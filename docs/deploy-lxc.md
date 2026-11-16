# Production install on a Debian LXC (no Docker)

Native Frappe bench install: MariaDB, bench's own Redis, gunicorn and
workers under supervisor, nginx in front. Tested on a Proxmox LXC
(Debian 13, 4 cores, 8 GB RAM).

## Container

- Debian 12 or 13, unprivileged, static LAN IP.
- 4 cores, 8 GB RAM (4 GB minimum), 2 GB swap or more, 40 GB disk or more.
- A `deploy` user with passwordless sudo and SSH key login. Everything below
  runs as `deploy`.

## 1. System packages

```bash
sudo apt-get update
sudo apt-get install -y git curl rsync ca-certificates build-essential pkg-config \
  mariadb-server mariadb-client libmariadb-dev redis-server nginx supervisor \
  cron xvfb libfontconfig1 fontconfig locales gnupg ansible-core fail2ban
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt-get install -y nodejs && sudo npm install -g yarn
curl -LsSf https://astral.sh/uv/install.sh | sh
echo 'export PATH=$HOME/.local/bin:$PATH' >> ~/.bashrc && . ~/.bashrc
uv python install 3.14
uv tool install frappe-bench
sudo systemctl disable --now redis-server   # bench runs its own Redis
sudo timedatectl set-timezone Africa/Casablanca   # the customer's time zone
```

Frappe 16 needs Python 3.14 and Node 24 (Debian ships older ones).
`ansible-core` and `fail2ban` are installed from Debian because
`bench setup production` otherwise tries to pip-install ansible and fails.

## 2. MariaDB

`/etc/mysql/mariadb.conf.d/99-frappe.cnf`:

```ini
[mysqld]
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
bind-address = 127.0.0.1
innodb_buffer_pool_size = 1G

[mysql]
default-character-set = utf8mb4
```

Generate the passwords on the server and keep them in files only `deploy`
can read:

```bash
sudo systemctl restart mariadb
umask 077; mkdir -p ~/secrets
head -c 32 /dev/urandom | base64 | tr -dc A-Za-z0-9 | head -c 28 > ~/secrets/db_root_password
head -c 32 /dev/urandom | base64 | tr -dc A-Za-z0-9 | head -c 20 > ~/secrets/admin_password
sudo mariadb -e "ALTER USER root@localhost IDENTIFIED VIA mysql_native_password USING PASSWORD('$(cat ~/secrets/db_root_password)') OR unix_socket; FLUSH PRIVILEGES;"
```

## 3. Bench, ERPNext and the app

```bash
cd ~
bench init frappe-bench --frappe-branch v16.56.0 --python "$(uv python find 3.14)"
cd frappe-bench
bench get-app --branch v16.55.0 erpnext
```

The app is copied from a tested commit on the workstation, so only
committed code reaches the server:

```bash
git archive --format=tar HEAD apps/retail_management frontend \
  | ssh deploy@<ip> 'rm -rf ~/src && mkdir -p ~/src && tar -xf - -C ~/src'
```

On the server, build the interface and install the app:

```bash
cd ~/src/frontend && npm ci && npm run build
cd ~/frappe-bench
cp -a ~/src/apps/retail_management apps/
(cd apps/retail_management && git init -q && git add -A && git commit -qm deploy)
uv pip install --python env/bin/python -e apps/retail_management
printf "frappe\nerpnext\nretail_management\n" > sites/apps.txt
```

## 4. Production processes

```bash
cd ~/frappe-bench
sudo env PATH=$HOME/.local/bin:/usr/sbin:/sbin:$PATH bench setup production deploy --yes
sudo ln -sf /home/deploy/frappe-bench/config/supervisor.conf /etc/supervisor/conf.d/frappe-bench.conf
sudo supervisorctl reread && sudo supervisorctl update
bench set-config -g live_reload false
chmod o+x /home/deploy    # nginx (www-data) must reach the static files
```

On Debian 13 bench writes the supervisor config but does not link it; the
`ln -sf` above does that.

Redis (ports 11000, 13000), gunicorn (8000) and MariaDB listen on
127.0.0.1 only. socket.io (9000) listens on all addresses and Frappe has no
option to change that, so a firewall blocks it. Install `nftables` and put
this in `/etc/nftables.conf`, then `sudo nft -f /etc/nftables.conf && sudo
systemctl enable nftables`:

```
flush ruleset
table inet filter {
	chain input {
		type filter hook input priority 0; policy drop;
		iif "lo" accept
		ct state established,related accept
		ct state invalid drop
		meta l4proto { icmp, ipv6-icmp } accept
		tcp dport { 22, 80, 443 } accept
	}
	chain forward { type filter hook forward priority 0; policy drop; }
	chain output { type filter hook output priority 0; policy accept; }
}
```

nginx still passes `/socket.io` to port 9000 locally, so live updates keep
working.

## 5. Site

Bench's Redis must be running (step 4) before this.

```bash
bench new-site <site> --db-root-username root \
  --db-root-password "$(cat ~/secrets/db_root_password)" \
  --admin-password "$(cat ~/secrets/admin_password)" \
  --install-app erpnext --install-app retail_management
bench use <site>
bench build --app retail_management     # links /assets/retail_management
bench --site <site> enable-scheduler
chmod 600 sites/<site>/site_config.json
sudo supervisorctl restart all
```

With one site, nginx serves it for any host name, so the LAN IP works.

Then, in a browser at `http://<ip>/app`, sign in as `Administrator` (password
in `~/secrets/admin_password`) and complete ERPNext's setup wizard (company,
country, currency). After that, create the owner's user with the Retail
Owner role, and the shops.

## 6. Backups

`~/bin/nightly-backup.sh`, run by cron at 02:30:

```sh
#!/bin/sh
set -eu
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
cd "$HOME/frappe-bench"
bench --site all backup --with-files --backup-path "$HOME/backups/$(date +%F)" >> "$HOME/backups/backup.log" 2>&1
find "$HOME/backups" -mindepth 1 -maxdepth 1 -type d -mtime +14 -exec rm -rf {} +
```

```bash
( crontab -l; echo "30 2 * * * $HOME/bin/nightly-backup.sh" ) | crontab -
```

`bench setup production` also adds a database-only backup every 6 hours
into `sites/<site>/private/backups`.

These copies are on the same disk as the site. A second copy outside the
container is still needed: Proxmox backups of the LXC (vzdump) and an
encrypted offsite copy (M1).

### Restore test

```bash
R="$(cat ~/secrets/db_root_password)"
bench new-site restoretest.local --db-root-username root --db-root-password "$R" --admin-password "$(head -c 24 /dev/urandom | base64)"
bench --site restoretest.local restore <dir>/<stamp>-<site>-database.sql.gz \
  --with-public-files <dir>/<stamp>-<site>-files.tar \
  --with-private-files <dir>/<stamp>-<site>-private-files.tar \
  --db-root-username root --db-root-password "$R"
bench --site restoretest.local list-apps
bench drop-site restoretest.local --force --no-backup --db-root-username root --db-root-password "$R"
```

## Updating the app

Copy the new commit with `git archive` as in step 3, then:

```bash
cd ~/src/frontend && npm ci && npm run build
rsync -a --delete --exclude .git ~/src/apps/retail_management/ ~/frappe-bench/apps/retail_management/
cd ~/frappe-bench
bench --site all backup
bench --site all migrate
sudo supervisorctl restart all
```
