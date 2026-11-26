# Deploy

The API runs on the VPS `74.208.250.12` at <https://crm.mithrandir.one>. The `deploy` job in `.github/workflows/ci.yml` runs on every push to `main` once `test`, `lint` and `stack` pass:

1. Builds the image and pushes it to `ghcr.io/stratastef/dating-crm:<commit sha>`.
2. Copies `compose.yaml` and `compose.prod.yaml` to `/opt/dating-crm/` on the VPS and writes `/opt/dating-crm/.env` from the `PRODUCTION_ENV` secret, plus `COMPOSE_FILE` and `IMAGE_TAG`.
3. Pulls the image and runs `docker compose up -d --wait`. The API runs `alembic upgrade head` as it starts.
4. Fails unless `GET https://crm.mithrandir.one/health` returns 200 within about a minute.

To roll back, open an older successful run of the CI workflow and re-run its `deploy` job.

## The VPS is shared

The VPS also runs the `vmte` project (`/opt/vmte`, deployed by another developer). Its Caddy container owns ports 80 and 443 and serves HTTPS for both projects:

- Our `api` container joins the Docker network `edge` under the alias `dating-crm-api`. The network was created once with `docker network create edge`.
- vmte's caddy service joins `edge` (in `/opt/vmte/deploy/docker-compose.yml`), and its Caddyfile (`/opt/vmte/deploy/Caddyfile`) has this site block:

  ```caddyfile
  # Dating CRM API (stratastef/dating-crm, deployed to /opt/dating-crm).
  crm.mithrandir.one {
  	encode zstd gzip
  	reverse_proxy dating-crm-api:8000
  }
  ```

  After editing the Caddyfile, reload Caddy without downtime: `docker exec vmte-caddy-1 caddy reload --config /etc/caddy/Caddyfile`.
- Both changes also have to land in the vmte repository, or vmte's next deploy drops them and this health check starts failing.
- Our compose file publishes no host ports: the host's port 5432 belongs to vmte's database.

## One-time setup

- DNS at Namecheap: an `A` record for `crm.mithrandir.one` pointing at `74.208.250.12`.
- The `deploy` user on the VPS is in the `docker` group, so its key is root-equivalent on the whole host, vmte included. Its password is locked; it logs in only with the key in `/home/deploy/.ssh/authorized_keys`.
- The deploy key pair. Generate it on your computer, give the public half to the VPS and the private half to GitHub:

  ```sh
  ssh-keygen -t ed25519 -N '' -C dating-crm-deploy -f ~/.ssh/dating_crm_deploy
  ssh root@74.208.250.12 'cat >> /home/deploy/.ssh/authorized_keys' < ~/.ssh/dating_crm_deploy.pub
  gh secret set DEPLOY_SSH_KEY --repo stratastef/dating-crm < ~/.ssh/dating_crm_deploy
  ```

- The `PRODUCTION_ENV` secret: the server's environment, one `NAME=value` per line, set with `gh secret set PRODUCTION_ENV --repo stratastef/dating-crm < production.env`. GitHub secrets cannot be read back, so keep the file in your password manager. It is the only copy of `TOKEN_VAULT_MASTER_KEY` outside the VPS: without it, a restored backup cannot decrypt any session token.

  ```sh
  # Never change these two after the first deploy. Postgres keeps the password it was created with,
  # and a new master key cannot decrypt the tokens already stored.
  # openssl rand -hex 32 (hex, because it goes inside DATABASE_URL)
  POSTGRES_PASSWORD=
  # openssl rand -base64 32 | tr '+/' '-_'
  TOKEN_VAULT_MASTER_KEY=
  ANTHROPIC_API_KEY=
  # Push notifications. APNS_KEY is the .p8 file's contents with line breaks written as \n.
  APNS_KEY=
  APNS_KEY_ID=
  APNS_TEAM_ID=
  APNS_BUNDLE_ID=
  # Google Calendar
  GOOGLE_CLIENT_ID=
  GOOGLE_CLIENT_SECRET=
  GOOGLE_REDIRECT_URI=https://crm.mithrandir.one/calendar/callback
  # SMS sign-in (ADR 0006)
  SMS_PROVIDER=twilio
  TWILIO_ACCOUNT_SID=
  TWILIO_AUTH_TOKEN=
  TWILIO_SENDER=
  JEV_BASE_URL=
  JEV_API_KEY=
  JEV_TOOL=
  JEV_MODEL=
  USER_TIMEZONE=
  ```

  Any other variable in `compose.yaml` can be added the same way. A variable reaches the containers only if `compose.yaml` passes it through.

## On the VPS

```sh
ssh deploy@74.208.250.12
cd /opt/dating-crm
docker compose ps
docker compose logs -f api worker
docker compose exec api python -m app.auth you@example.com   # create a user and print their token
```
