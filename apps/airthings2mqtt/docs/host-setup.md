# Host Setup

The Docker host needs the settings below. Each section says whether the setting is
required and why. The values were tested against Debian 13 with BlueZ 5.82 and
dbus-daemon 1.16.2.

| Setting                                         | Required?                  |
| ----------------------------------------------- | -------------------------- |
| [Host account for UID 10001](#container-user-uid-10001) | **Yes**, from 0.3.0 |

---

## Container User (UID 10001)

From 0.3.0 the image runs as a dedicated user, UID and GID **10001**. Earlier releases
used UID 1000.

**Why a dedicated UID.** On most hosts UID 1000 is the first login account, often with
`sudo`. A host D-Bus policy aimed at UID 1000 would also restrict that person. UID
10001 belongs to airthings2mqtt alone, so a host D-Bus policy can target the app and
nothing else.

**Why the host needs an account for it.** The container talks to BlueZ through the
host's system bus. dbus-daemon resolves the caller's UID in the **host's** user
database and refuses the connection when there is no account for it. Without one, the
app cannot reach BlueZ at all and every poll fails.

Create a system account with no login, home directory or extra groups:

```bash
sudo groupadd --system --gid 10001 airthings2mqtt
sudo useradd --system --uid 10001 --gid 10001 --no-create-home \
    --shell /usr/sbin/nologin airthings2mqtt
id airthings2mqtt   # uid=10001(airthings2mqtt) gid=10001(airthings2mqtt) groups=10001(airthings2mqtt)
```

`useradd` may warn that 10001 is above `SYS_UID_MAX`. That is harmless. Do not add the
account to `bluetooth`, `netdev` or any other group: the default BlueZ policy already
lets every account scan, connect and read.

If `getent passwd 10001` or `getent group 10001` already prints an entry, `useradd`
fails. Reuse that entry only if it is not a person's login account: the image and the
policy file both hardcode 10001, and the policy would restrict whoever owns it.

### Upgrading from 0.2.x

The data directory still belongs to UID 1000, so the app cannot write
`/app/data/store.json` (`Permission denied` in the logs). Docker copies the image's
ownership into a named volume only when it creates the volume, so an existing
`airthings2mqtt-data` volume keeps the old owner. A bind mount never changes owner.

Fix the ownership once, after creating the host account and before starting the new
image. This command works for both named volumes and bind mounts, because it uses the
service's own mounts:

```bash
docker compose pull airthings2mqtt
docker compose stop airthings2mqtt
docker compose run --rm --no-deps --user 0:0 --entrypoint chown \
    airthings2mqtt -R 10001:10001 /app/data
docker compose run --rm --no-deps --entrypoint ls airthings2mqtt -ln /app/data
docker compose up -d airthings2mqtt
```

The `ls` should show `10001 10001` for every file. For a bind mount you can instead
run `sudo chown -R 10001:10001 <host data directory>` on the host. With several
airthings2mqtt services, repeat the `chown` for each service name.
