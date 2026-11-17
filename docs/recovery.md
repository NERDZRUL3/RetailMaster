# Getting back in: forgotten passwords and a lost server

What to do when someone cannot sign in, or when the server itself is out of
reach. Work down the list: each step needs a little more access than the one
before it.

| Situation | Who can fix it | How |
|---|---|---|
| A staff member forgot their password | An owner | Team page → the person → set a new password |
| An owner forgot their password | The owner | Sign-in page → **Forgot your password?** → email link or recovery code |
| Every owner is locked out, the server still runs | Whoever has SSH or Proxmox access | `bench set-password` on the server |
| SSH key lost, Proxmox still works | Whoever can sign in to Proxmox | Container console from Proxmox |
| The server or its disk is gone | Whoever holds the offsite passwords | Rebuild from the encrypted offsite copy |

## 1. Owner forgot their password

On the sign-in page, **Forgot your password?** offers:

- **Email link.** Shown only when the site can send email (an outgoing Email
  Account in the desk: *Email Account* → new → tick *Enable Outgoing* and
  *Default Outgoing*). The link opens Frappe's own *Set new password* page.
  It never works for `Administrator`.
- **Recovery code.** Owners make ten single-use codes in **Settings →
  Recovery codes** and print, download or copy them. One code plus the
  account's email or username sets a new password, and unlocks the account
  if it was locked after wrong passwords. Making a new set cancels the old
  one. Codes are stored only as hashes; nobody, including the server admin,
  can read them back. Attempts are limited to 10 per hour.

Make codes as soon as an owner account is created, and again when few are
left (the Settings page shows how many remain).

## 2. Every owner is locked out, the server still runs

```bash
ssh -i ~/.ssh/retailmaster_lxc deploy@<server>
cd ~/frappe-bench
bench --site retail.local set-password owner@example.com      # asks for the new password
bench --site retail.local set-admin-password                    # Administrator
```

The Administrator password chosen at installation is in
`~/secrets/admin_password` on the server.

## 3. SSH key lost, Proxmox still works

In the Proxmox web interface: the container → **Console**, or on the Proxmox
host shell: `pct enter <container id>`. Then add a new public key:

```bash
su - deploy
echo 'ssh-ed25519 AAAA... new-key' >> ~/.ssh/authorized_keys
```

Keep a second SSH key (on another computer, or in a password manager) so
losing one laptop never locks you out.

## 4. Server lost: rebuild from the offsite copy

Every night after the local backup, `~/bin/offsite-backup.sh`
(`deploy/offsite-backup.sh`) uploads an **encrypted** copy to cloud storage
with rclone, one folder per day, kept 30 days. Each folder holds:

- `backup/`: the database dump and the public and private files
- `server/secrets/`: the generated database root and Administrator passwords
- `server/sites/<site>/site_config.json`: includes the site's
  **encryption key**; without it saved passwords and encrypted settings
  cannot be restored
- `server/versions.txt`: Frappe, ERPNext and app versions of that night

### What you must keep outside the server

The encryption happens on the server with two passwords that are stored in
`~/.config/rclone/rclone.conf` there. **If the server is lost, so are they.**
Keep these in your password manager or on paper, away from the server:

1. The cloud storage account (e.g. Google Drive) sign-in
2. The rclone crypt **password** and **salt** (password2) you typed during
   setup
3. An SSH key and this document

### One-time setup on the server

```bash
ssh -i ~/.ssh/retailmaster_lxc deploy@<server>
rclone config
```

1. `n` new remote, name `offsite`, pick your storage (e.g. `drive` for Google
   Drive). For Google Drive, answer `n` to "Use web browser to automatically
   authenticate?" and follow the printed instructions: run the given
   `rclone authorize ...` command on your own PC, sign in there, and paste
   the token back.
2. `n` new remote, name `offsite-crypt`, type `crypt`, remote
   `offsite:retailmaster-backup`, filename encryption `standard`, directory
   name encryption `true`, then **type your own password and salt** (choose
   `y` "type in my own password") and save both in your password manager
   right now.
3. Test: `~/bin/offsite-backup.sh && tail -n 3 ~/backups/offsite.log`, then
   `rclone ls offsite-crypt:retailmaster | head`.

Until this is done, the nightly job logs
`FAILED: rclone remote 'offsite-crypt' is not set up` in
`~/backups/offsite.log`; the local backup is not affected.

### Restoring on a new server

1. Build a new container and install the stack as in
   [deploy-lxc.md](deploy-lxc.md) sections 1 to 4 (do not create the site yet).
2. Install rclone and recreate both remotes with **the same** crypt password
   and salt (`rclone config`, as above).
3. Fetch the newest copy:

   ```bash
   rclone lsd offsite-crypt:retailmaster
   rclone copy offsite-crypt:retailmaster/<YYYY-MM-DD> ~/restore
   ```

4. Put the secrets back, create the site with the old encryption key, and
   restore:

   ```bash
   mkdir -p ~/secrets && cp ~/restore/server/secrets/* ~/secrets/ && chmod 600 ~/secrets/*
   cd ~/frappe-bench
   R="$(cat ~/secrets/db_root_password)"
   bench new-site retail.local --db-root-username root --db-root-password "$R" \
     --admin-password "$(cat ~/secrets/admin_password)"
   KEY=$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/restore/server/sites/retail.local/site_config.json')))['encryption_key'])")
   bench --site retail.local set-config encryption_key "$KEY"
   bench --site retail.local restore ~/restore/backup/*-database.sql.gz \
     --with-public-files ~/restore/backup/*-files.tar \
     --with-private-files ~/restore/backup/*-private-files.tar \
     --db-root-username root --db-root-password "$R"
   bench --site retail.local migrate
   ```

5. Finish with sections 5 to 7 of [deploy-lxc.md](deploy-lxc.md) (production
   setup, backups, Cloudflare), then point the Cloudflare tunnel hostnames at
   the new server's address.
6. Sign in and check: dashboard figures, a product, the last till session.
