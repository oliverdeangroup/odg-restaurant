# Installing ODG-RESTAURANT on the cPanel server

Server: AlmaLinux 8 + WHM/cPanel + LiteSpeed + CSF (the same server as ODG-SCHOOL).
ODG-RESTAURANT runs inside the cPanel account **`restaurant`** on port **8002**
(ODG-SCHOOL uses 8001), next to the WordPress sites, without touching them.

```
Browser ──https──► restaurant.oliverdeangroup.com
                     │  NGINX → LiteSpeed (AutoSSL certificate)
                     ▼
       Gunicorn + Django on 127.0.0.1:8002  (user "restaurant")
                     │
                MySQL restaurant_app (cPanel)   Uploads/bills/backups: ~/odg-data
```

Steps marked **(root)** are run in **WHM → Terminal**. All other steps run as
`restaurant` (`ssh restaurant`).

## 1. Domain and SSL
`restaurant.oliverdeangroup.com` is the main domain of the `restaurant` account.
Check that AutoSSL issued the certificate: cPanel → SSL/TLS Status.

## 2. Database
cPanel (`restaurant`) → **MySQL Databases**: database `restaurant_app`, user
`restaurant_master` with **ALL PRIVILEGES**. (Done with `uapi` during the install.)

## 3. The code
```bash
cd ~
git clone git@github.com:oliverdeangroup/odg-restaurant.git odg-restaurant
cd odg-restaurant
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
mkdir -p ~/odg-data run
```

## 4. Settings file
```bash
cp .env.example .env && chmod 600 .env && nano .env
```
Fill in `SECRET_KEY`, `DB_PASSWORD` and `DATA_DIR=/home/restaurant/odg-data`.

## 5. Database tables, demo and first administrator
```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py setup_odg --admin <username> --email <e-mail>
.venv/bin/python manage.py demo_build
.venv/bin/python manage.py check --deploy
```

## 6. Start the app (root)
```bash
cp /home/restaurant/odg-restaurant/deploy/odg-restaurant.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now odg-restaurant
curl -sI http://127.0.0.1:8002/ | head -1
```

## 7. Connect LiteSpeed (root)
1. WHM → LiteSpeed Web Server → WebAdmin Console → **Configuration → Server → External App → Add**:
   Type **Web Server**, Name `odgrestaurant`, Address `127.0.0.1:8002`, Max Connections `100`,
   Initial Request Timeout `120`, Retry Timeout `0`. Save, then **Graceful Restart**.
2. As `restaurant`: `cat ~/odg-restaurant/deploy/htaccess.txt >> ~/public_html/.htaccess`
3. Turn the NGINX cache off for the account (root):
   `/usr/local/cpanel/scripts/ea-nginx cache restaurant --enabled=0`
4. cPanel (`restaurant`) → Domains → **Force HTTPS Redirect** on.

## Updating later
- **ZIP**: Settings → Updates → upload → check → Install. A backup is made first.
- **GitHub**: `ssh restaurant 'cd odg-restaurant && ./deploy.sh'`

Updates never remove user data: uploads, bills and backups live in `~/odg-data`, the
database only changes through migrations (a migration that deletes tables or fields is
blocked unless confirmed), and a full export is made before every update.

## Useful commands
```bash
systemctl restart odg-restaurant          # (root) restart the app
tail -f ~/odg-restaurant/run/error.log    # errors
```
