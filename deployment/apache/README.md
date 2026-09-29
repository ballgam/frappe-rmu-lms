# Apache reverse proxy for the RMU Somalia LMS

Apache terminates TLS and forwards the public LMS hostname to the Docker stack
listening on `127.0.0.1:8080`. The stack itself is described in
[../README.md](../README.md); this document only covers the Apache host.

Templates in this directory:

- `rmu-lms-http.conf.example` — bootstrap vhost used before a certificate exists.
- `rmu-lms-ssl.conf.example` — production vhost with TLS, redirect, and WebSockets.

Replace every `LMS_DOMAIN` token with the real hostname. The Frappe site name
(`SITE_NAME` in `deployment/.env`) must exactly match that hostname.

## 1. Install Apache

### Ubuntu 24.04

```bash
sudo apt update
sudo apt install -y apache2
sudo a2enmod proxy proxy_http headers rewrite ssl
sudo systemctl enable --now apache2
```

On Ubuntu the proxy and rewrite modules are already loaded on most installs;
enabling them again is safe. The default site is disabled in step 3.

### RHEL 8/9 (and compatible: Rocky, AlmaLinux)

```bash
sudo dnf install -y httpd mod_ssl
sudo systemctl enable --now httpd
```

RHEL ships `mod_proxy`, `mod_proxy_http`, `mod_headers`, and `mod_rewrite`
enabled by default. Confirm the proxy modules are present:

```bash
httpd -M | grep -E 'proxy_module|proxy_http_module|headers_module|rewrite_module|ssl_module'
```

### Firewall

```bash
# Ubuntu (ufw)
sudo ufw allow 'Apache Full'

# RHEL (firewalld)
sudo firewall-cmd --permanent --add-service=http --add-service=https
sudo firewall-cmd --reload
```

Only ports 80 and 443 are public. Port 8080 stays bound to loopback and is never
exposed; do not open it in the firewall.

## 2. Open the local port

The vhosts proxy to `127.0.0.1:8080`, which is the `FRONTEND_BIND` value in
`deployment/.env`. If the deploy script chose a different port, edit the two
`ProxyPass`/`ProxyPassReverse` lines in both templates to match. Confirm the
stack is listening before enabling the vhost:

```bash
ss -ltnp | grep 8080
curl --fail --header "Host: LMS_DOMAIN" http://127.0.0.1:8080/api/method/ping
```

## 3. Certificate

The example vhosts expect Let's Encrypt certificates under
`/etc/letsencrypt/live/LMS_DOMAIN/`. Certbot writes
`/etc/letsencrypt/options-ssl-apache.conf`, which the SSL vhost includes.

### Ubuntu

```bash
sudo apt install -y certbot python3-certbot-apache
```

### RHEL 8/9

```bash
sudo dnf install -y certbot python3-certbot-apache
```

### Issue the certificate

DNS for `LMS_DOMAIN` must already resolve to this host and port 80 must be
reachable before running Certbot.

1. Enable the HTTP bootstrap vhost so port 80 answers for the domain:

   ```bash
   sudo cp rmu-lms-http.conf.example /etc/apache2/sites-available/rmu-lms.conf   # Ubuntu
   sudo cp rmu-lms-http.conf.example /etc/httpd/conf.d/rmu-lms.conf              # RHEL
   # then edit the copy and replace LMS_DOMAIN
   sudo a2ensite rmu-lms && sudo systemctl reload apache2                        # Ubuntu
   sudo systemctl reload httpd                                                   # RHEL
   ```

2. Request the certificate and let Certbot install the HTTPS vhost:

   ```bash
   sudo certbot --apache -d LMS_DOMAIN
   ```

   Certbot creates the `:443` vhost and adds the `:80` redirect. If you prefer
   to manage the vhost by hand, use `certbot certonly --apache -d LMS_DOMAIN`
   and then install `rmu-lms-ssl.conf.example` yourself in step 4.

3. Renewal is automated by the `certbot.timer` systemd unit (Ubuntu) or the
   `certbot-renew.timer` unit (RHEL). Verify it is active and do a dry run:

   ```bash
   systemctl list-timers | grep certbot
   sudo certbot renew --dry-run
   ```

Certificates are valid for 90 days and renew automatically. Keep port 80 open
for the HTTP-01 challenge even after switching to HTTPS.

## 4. Production vhost

If Certbot did not generate the vhost, install the TLS template manually.

Ubuntu (Debian layout):

```bash
sudo cp rmu-lms-ssl.conf.example /etc/apache2/sites-available/rmu-lms.conf
sudo nano /etc/apache2/sites-available/rmu-lms.conf   # replace LMS_DOMAIN
sudo a2ensite rmu-lms
sudo a2dissite 000-default
sudo apachectl configtest
sudo systemctl reload apache2
```

RHEL (single-directory layout; there is no `a2ensite`):

```bash
sudo cp rmu-lms-ssl.conf.example /etc/httpd/conf.d/rmu-lms.conf
sudo vi /etc/httpd/conf.d/rmu-lms.conf                # replace LMS_DOMAIN
sudo apachectl configtest
sudo systemctl reload httpd
```

On RHEL the `${APACHE_LOG_DIR}` variable is defined by `httpd`, so the log
directives work unchanged. The template handles all required behaviour:

| Requirement | Directive |
| --- | --- |
| Preserve the public hostname | `ProxyPreserveHost On` |
| Tell Frappe it is behind HTTPS | `RequestHeader set X-Forwarded-Proto "https"` |
| WebSocket upgrades for realtime | `/socket.io/` `ProxyPass ... upgrade=websocket` |
| Allow 2 GB uploads | `LimitRequestBody 0` (inner Nginx enforces `2g`) |
| Long video uploads | `timeout=660` / `ProxyTimeout 660` |
| HSTS | `Header always set Strict-Transport-Security` |

The `upgrade=websocket` parameter requires Apache 2.4.47 or newer. On older
builds, replace it with a dedicated `mod_proxy_wstunnel` vhost:

```apache
<Location /socket.io/>
    ProxyPass ws://127.0.0.1:8080/socket.io/
    ProxyPassReverse ws://127.0.0.1:8080/socket.io/
</Location>
```

## 5. SELinux (RHEL)

With SELinux enforcing, allow Apache to open the outbound proxy connection:

```bash
sudo setsebool -P httpd_can_network_connect 1
```

Verify the context and denials:

```bash
getenforce
sudo ausearch -m AVC -ts recent
```

## 6. Verify

```bash
# Config syntax
sudo apachectl configtest

# HTTP redirects to HTTPS
curl -sI http://LMS_DOMAIN | grep -i location

# Public HTTPS reaches the app
curl --fail https://LMS_DOMAIN/api/method/ping

# WebSocket endpoint upgrades (expect HTTP 101 after the handshake)
curl -i -N \
  -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  https://LMS_DOMAIN/socket.io/?EIO=4\&transport=websocket
```

Then load the site in a browser and confirm realtime features (notifications,
live updates) work, which proves the WebSocket route is correct.

## 7. Troubleshooting

| Symptom | Check |
| --- | --- |
| 502 Bad Gateway | Stack down or on another port: `ss -ltnp \| grep 8080`, then `../scripts/compose-cli.sh --env-file .env ps`. |
| 400 / wrong site | `SITE_NAME` in `deployment/.env` must equal `LMS_DOMAIN`; confirm `ProxyPreserveHost On`. |
| Redirect loops | `X-Forwarded-Proto` must be `https` on the TLS vhost and `http` on the bootstrap vhost only. |
| Realtime not working | `/socket.io/` WebSocket route or Apache older than 2.4.47. |
| Uploads fail at ~1 GB | `LimitRequestBody` still set; it must be `0` and the inner Nginx `CLIENT_MAX_BODY_SIZE` must be `2g`. |
| SELinux denials | `setsebool -P httpd_can_network_connect 1`. |
| Cert renewal fails | Port 80 open and DNS unchanged; run `sudo certbot renew --dry-run`. |

Logs:

```bash
sudo tail -f /var/log/apache2/rmu-lms-ssl-error.log   # Ubuntu
sudo tail -f /var/log/httpd/rmu-lms-ssl-error.log     # RHEL
```
