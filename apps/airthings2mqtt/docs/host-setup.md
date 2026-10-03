# Host Setup

The Docker host needs the settings below. Each section says whether the setting is
required and why. The values were tested against Debian 13 with BlueZ 5.82 and
dbus-daemon 1.16.2.

| Setting                                         | Required?                  |
| ----------------------------------------------- | -------------------------- |
| [Host account for UID 10001](#container-user-uid-10001) | **Yes**, from 0.3.0 |
| [No added capabilities, `no-new-privileges`](#capabilities-and-no-new-privileges) | Recommended |
| [Deny BlueZ property writes](#optional-deny-bluez-property-writes) | Optional |
| [Image 0.3.0+ before adding the health check](#health-check-needs-030-or-later) | **Yes**, with the `healthcheck` block |

---

## Container User (UID 10001)

From 0.3.0 the image runs as a dedicated user, UID and GID **10001**. Earlier releases
used UID 1000.

**Why a dedicated UID.** On most hosts UID 1000 is the first login account, often with
`sudo`. A host D-Bus policy aimed at UID 1000 would also restrict that person. UID
10001 belongs to airthings2mqtt alone, so the
[BlueZ write policy](#optional-deny-bluez-property-writes) can target the app and
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

---

## Capabilities and `no-new-privileges`

Releases before 0.3.0 shipped `cap_add: [NET_ADMIN, SYS_ADMIN]`. The shipped
`compose.yml` now adds no capabilities and sets:

```yaml
security_opt:
  - no-new-privileges:true
```

**Why the capabilities went.** BLE goes through BlueZ over the D-Bus socket. BlueZ
runs on the host and does the privileged work itself, so the app needs no capability.
Host testing confirmed that the non-root process had no effective capabilities even
with `cap_add` (`CapEff: 0000000000000000` in `/proc/1/status`). The entries only
widened the bounding set. A process that executed a setuid or file-capability binary
could have picked up `CAP_NET_ADMIN`, which is enough to drive the kernel Bluetooth
management socket and power the adapter off without going through D-Bus.

**Why `no-new-privileges`.** It stops any process in the container from gaining
privileges through setuid binaries or file capabilities. The app never needs to, so
the option costs nothing and closes that path.

**If you use your own compose file**, delete the `cap_add` block from the
airthings2mqtt service and add the `security_opt` above. Check the result:

```bash
C=$(docker compose ps -q airthings2mqtt)
docker inspect --format '{{.HostConfig.CapAdd}} {{.HostConfig.SecurityOpt}}' "$C"
# expect: [] [no-new-privileges:true]
docker exec "$C" grep -E '^Cap(Eff|Bnd)' /proc/1/status
```

`CapEff` must be all zeros. `CapBnd` should no longer include bit 12 (`0x1000`,
`cap_net_admin`) or bit 21 (`0x200000`, `cap_sys_admin`).

---

## Health Check Needs 0.3.0 or Later

The image and the shipped `compose.yml` run `airthings2mqtt health` every 60 seconds.
The `health` command first ships in 0.3.0, the release that contains
[PR #323](https://github.com/ff-fab/cosalette-apps/pull/323). Upgrade the image before
you copy the `healthcheck` block into your own compose file.

This matters if you pin a tag. The 0.2.x CLI ignores its arguments, so
`airthings2mqtt health` on an old image does not check anything: it starts a **second
instance** of the app inside the container. That instance connects with the same MQTT
client ID, so the broker disconnects the running app, and both poll the sensor. Docker
kills the probe after `timeout` and marks the container `unhealthy`, then repeats this
every `interval`.

Check the image before enabling the health check:

```bash
docker compose run --rm --no-deps airthings2mqtt airthings2mqtt health
# 0.3.0+: "unhealthy: ... does not exist" (exit 1) in a fresh container. Good.
# 0.2.x: app startup logs and an MQTT connection. Press Ctrl+C and upgrade first.
```

The image's own `HEALTHCHECK` only exists from 0.3.0, so an old image without the
compose block is not affected.

---

## Optional: Deny BlueZ Property Writes

airthings2mqtt never power-cycles the adapter
([ADR-003](adr/ADR-003-no-adapter-power-cycling-bluetooth-adapter-recovery-is-host-side.md)),
but that is a rule about its code. On a stock Debian host the BlueZ D-Bus policy
(`/usr/share/dbus-1/system.d/bluetooth.conf`) lets **every** local account call
`org.freedesktop.DBus.Properties.Set` on BlueZ, including setting
`Adapter1.Powered`. Host testing confirmed this from inside the container. The read-only
`/var/run/dbus` mount does not help: it protects the socket file, not the messages
sent through it.

To enforce the rule on the host, install the policy file shipped in
[`deploy/airthings2mqtt-bluez.conf`](https://github.com/ff-fab/cosalette-apps/blob/main/apps/airthings2mqtt/deploy/airthings2mqtt-bluez.conf):

```xml
<busconfig>
  <policy user="10001">
    <deny send_destination="org.bluez"
          send_interface="org.freedesktop.DBus.Properties"
          send_member="Set"/>
  </policy>
</busconfig>
```

It denies one D-Bus call, `Properties.Set` addressed to BlueZ, and only for UID 10001.
It is opt-in. The app works the same with or without it.

**Why it does not break the app.** The app never calls `Properties.Set`. It only
scans (`SetDiscoveryFilter`, `StartDiscovery`, `StopDiscovery`), connects, reads GATT
characteristics, and reads properties and signals. A review of the bleak BlueZ backend
found one `Properties.Set`: setting `Device1.Trusted` while pairing. bleak only does
that for `connect(pair=True)` or `pair()`, and airthings2mqtt uses neither.

### Install

On the Docker host:

```bash
curl -fsSL https://raw.githubusercontent.com/ff-fab/cosalette-apps/main/apps/airthings2mqtt/deploy/airthings2mqtt-bluez.conf \
    -o airthings2mqtt-bluez.conf
sudo install -m 0644 -o root -g root airthings2mqtt-bluez.conf /etc/dbus-1/system.d/
sudo systemctl reload dbus
```

The reload applies the policy to existing connections, so the container needs no
restart. dbus-daemon also picks up new files in `system.d` by itself within a few
seconds. If `systemctl reload dbus` is not available, send the reload request
directly:

```bash
sudo dbus-send --system --print-reply --dest=org.freedesktop.DBus \
    / org.freedesktop.DBus.ReloadConfig
```

A syntax error makes dbus-daemon keep the previous configuration and log the problem
(`journalctl -u dbus`). The file was tested with dbus-daemon 1.16.2. Hosts that run
dbus-broker instead were not tested.

### Verify

Run these on the host while the container is running:

```bash
C=$(docker compose ps -q airthings2mqtt)

# 1. A write is refused. The deliberately wrong value type means that, without the
#    policy, BlueZ rejects it with InvalidSignature and the adapter stays on.
docker exec "$C" dbus-send --system --print-reply --dest=org.bluez /org/bluez/hci0 \
    org.freedesktop.DBus.Properties.Set \
    string:org.bluez.Adapter1 string:Powered variant:string:probe
# expect: Error org.freedesktop.DBus.Error.AccessDenied

# 2. Reads still work.
docker exec "$C" dbus-send --system --print-reply --dest=org.bluez /org/bluez/hci0 \
    org.freedesktop.DBus.Properties.Get string:org.bluez.Adapter1 string:Powered
# expect: variant boolean true

# 3. Scanning still works.
docker exec "$C" timeout 20 bluetoothctl --timeout 15 scan on
# expect: [NEW] Device lines
```

Then wait for the next poll, or trigger one with
`mosquitto_pub -h localhost -t "airthings2mqtt/airthings/set" -n`, and check that a new
reading arrives on `airthings2mqtt/airthings/state`. If step 1 still prints
`InvalidSignature`, the policy is not active: check the file path, the reload, and that
the container runs as UID 10001 (`docker exec "$C" id -u`).

### What It Blocks and What It Does Not

dbus-daemon applies the default policy first, then group policies, then user policies,
then `mandatory` ones. A later rule wins, so this user rule overrides the allow in
`bluetooth.conf` and in any `group=` policy. A distribution policy with
`context="mandatory"` that allows BlueZ writes would override it. Debian ships none;
check with `grep -rl mandatory /etc/dbus-1 /usr/share/dbus-1`.

For UID 10001 it blocks **every** BlueZ property write, not only `Powered`:

- `Adapter1`: `Powered`, `Discoverable`, `DiscoverableTimeout`, `Pairable`,
  `PairableTimeout`, `Alias`
- `Device1`: `Trusted`, `Blocked`, `Alias`, `WakeAllowed`
- any other BlueZ object's writable properties

The app needs none of these. Anything else you run as UID 10001 loses them too, which
is a reason to keep that UID for this app alone.

It does **not** block BlueZ methods, which are separate D-Bus calls. UID 10001 can
still call `Device1.Connect`, `Disconnect`, `Pair`, `Adapter1.RemoveDevice`,
`StartDiscovery` and GATT `WriteValue`. Nor does it touch the kernel Bluetooth
management socket, which the
[capabilities section](#capabilities-and-no-new-privileges) covers. Other accounts on
the host, including your login and root, are unaffected.

The policy targets the UID, not the container. A 0.2.x image runs as UID 1000 and is
not covered.

### Remove

```bash
sudo rm /etc/dbus-1/system.d/airthings2mqtt-bluez.conf
sudo systemctl reload dbus
```
