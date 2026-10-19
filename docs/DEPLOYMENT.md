# Hosted college-project demo

Deployed 12 October 2026.

- **Game:** [quriousminds.vercel.app](https://quriousminds.vercel.app)
- **API:** [Cloud Run health](https://quriousminds-api-285568391757.asia-south1.run.app/api/health)
- **Frontend:** Vercel project `quriousminds`, Next.js, linked from `client/`.
- **Backend:** Cloud Run service `quriousminds-api`, project
  `project-8c50e5eb-7ddd-4a46-9c8`, region `asia-south1`.

The backend uses one Python process, 512 MiB memory, one CPU, a maximum of one
instance, and a 60-minute request timeout for WebSockets. It scales to zero when
idle. Open sockets keep a Cloud Run instance active and can incur cloud charges.

Rooms are held in memory: an instance restart or redeployment resets games. The
single-instance setting is essential for this demo; horizontal scaling requires
a shared room store. Seat recovery works while the instance remains alive.

## What is actually deployed (read this before trusting anything else)

Two different things are easy to confuse, so they are separated here.

**Implemented in this repository, verified by tests:** the opt-in live-hardware path
(a room resolves an Observe / Level-4 decoherence collapse with one IBM Quantum
measurement when `QISKIT_IBM_TOKEN` is configured), its explicit refusal behaviour,
and the client's pending/error surfaces. It is exercised by `tests/test_hardware_collapse.py`
against a **mocked** IBM boundary.

**Deployed in the hosted demo above:** the ordinary sealed toy-engine game, the
Next.js client, and the music/seat-recovery behaviour. The demo does **not** set
`QISKIT_IBM_TOKEN`, so `quantum.enabled` is `false` for every room and **the hosted
demo has never measured a collapse on real hardware**. No result in this repository
comes from real hardware; one local one-shot job is recorded in `docs/HANDOFF.md` to
confirm the path. Enabling it is an operator action, documented below; it was not
performed as part of the code change.

Nothing in this document claims a deployment or a hardware run that was not actually
performed and recorded.

## Redeploy

From the repository root:

```powershell
gcloud run deploy quriousminds-api --source . `
  --project project-8c50e5eb-7ddd-4a46-9c8 --region asia-south1 `
  --allow-unauthenticated --port 8080 --cpu 1 --memory 512Mi `
  --min-instances 0 --max-instances 1 --timeout 3600 --concurrency 80 `
  --session-affinity `
  --service-account quriousminds-runtime@project-8c50e5eb-7ddd-4a46-9c8.iam.gserviceaccount.com `
  --build-service-account projects/project-8c50e5eb-7ddd-4a46-9c8/serviceAccounts/quriousminds-build@project-8c50e5eb-7ddd-4a46-9c8.iam.gserviceaccount.com

cd client
npx vercel deploy --prod --yes --scope asterisk-hunters-projects
```

The dedicated build account has the Cloud Run Builder role. The runtime account
has no additional project roles. `Dockerfile`, `requirements-server.txt`,
`.dockerignore`, and `.gcloudignore` keep the game-server image and upload small.

Vercel Production and Preview both have `NEXT_PUBLIC_API_URL` set to the Cloud Run
HTTPS origin. WSS is derived from that value. If the backend URL changes, update
the Vercel variable and redeploy: Next.js inlines it during the build.

## IBM Quantum and the offline mode

Gameplay uses `DeterministicToyEngine`, preserving the reported experiment rules. The live
server has exactly two modes:

* **Offline (default).** With no `QISKIT_IBM_TOKEN`, the ordinary game runs on the CPU
  engine: no simulator, no circuits, and no job is submitted.
* **Live hardware (opt-in).** When `QISKIT_IBM_TOKEN` is set, a live room resolves each
  collapse (Observe, or the Level-4 decoherence expiry) with one measurement shot on IBM
  hardware. If the key, instance, backend or job is unavailable, the move is refused with
  error code `quantum_unavailable` and the game state is left unchanged. If the measured
  bitstring maps to no candidate square (an unused basis state, or hardware noise), the
  move is refused with `quantum_invalid_outcome` and the state is likewise unchanged.
  There is no simulator or random substitution on this path -- **nothing is ever
  substituted for a refused outcome**.

For the live path, install the server's IBM requirements and set the variables
privately in the environment. Never put IBM keys in `NEXT_PUBLIC_*` and never commit
them:

```bash
python -m pip install -r requirements-server.txt   # includes the IBM Runtime SDK
# QCHECKERS_DISABLE_HARDWARE=1   # optional hard off-switch for a server
# QISKIT_IBM_TOKEN=<api key>       # enables the live path; legacy IBM key names are ignored
# IBM_QUANTUM_INSTANCE=<crn>     # recommended instance CRN
# IBM_QUANTUM_BACKEND=<device>   # optional named device, else least-busy
# IBM_QUANTUM_TIMEOUT=<seconds>  # default 180; the wait runs off the event loop
```

Each collapse re-prepares a fresh circuit from the stored distribution and submits one
shot; no qubit stays loaded between turns. The blocking IBM wait runs on a worker
thread under a per-room lock, so the API loop stays free and two players can never
apply concurrent moves to the same room. Each `StateUpdate` carries a `quantum` block
(`enabled`, `backend`, `last`) and a `quantum_pending` flag so the browser can name the
backend and show the pending state. No credential ever appears in a payload, log or
error message.

To exercise the live path manually, install the server's IBM-enabled dependencies and
start the server with the variables set in the shell:

```powershell
python -m pip install -r requirements-server.txt   # includes the IBM Runtime SDK
$env:QISKIT_IBM_TOKEN="<api key>"      # enables the live path
$env:IBM_QUANTUM_INSTANCE="<crn>"      # recommended instance CRN
$env:IBM_QUANTUM_BACKEND="<device>"    # optional; otherwise least-busy
python -m server                       # http://127.0.0.1:8000
```

The server reads plain environment variables and does **not** auto-load a `.env` file:
set them in the shell — on Windows, `$env:QISKIT_IBM_TOKEN="..."` — or load them yourself
before starting the server. Open a room in the client and play to the first collapse
(Observe, or a Level-4 decoherence expiry); the server submits one measurement shot to
IBM Quantum and writes the measured square into game state. A refused outcome
(`quantum_invalid_outcome` or `quantum_unavailable`) leaves the board unchanged and the
client shows the error. The full design and verification record is in
[`HARDWARE_COLLAPSE.md`](HARDWARE_COLLAPSE.md).

The public game API never accepts credentials from clients; it reads the IBM token from
the server environment only and submits one collapse shot per collapsing action when that
token is present. Never put IBM keys in `NEXT_PUBLIC_*` variables or commit them to source
control. The legacy names `IBM_CLOUD_API_KEY` and `IBM_QUANTUM_API_KEY` are ignored;
only `QISKIT_IBM_TOKEN` enables the live path.

### Enabling the live-hardware path on Cloud Run (operator runbook)

The live path is **off** unless `QISKIT_IBM_TOKEN` is present in the service
environment. The hosted demo does not set it. To enable it without leaking the key into
source, the image, the frontend bundle, logs, or your shell history:

1. In Google Cloud Console, open **Security → Secret Manager → Create secret**. Name it
   `ibm-quantum-token`, paste the IBM API key into the secret value field, and create the
   secret. Do not put the key in a command, a file in the repository, or a Vercel
   variable. Secret Manager keeps the value out of command history and deployment source.

2. Let the runtime service account read that secret:

   ```bash
   gcloud secrets add-iam-policy-binding ibm-quantum-token \
     --member=serviceAccount:quriousminds-runtime@project-8c50e5eb-7ddd-4a46-9c8.iam.gserviceaccount.com \
     --role=roles/secretmanager.secretAccessor \
     --project project-8c50e5eb-7ddd-4a46-9c8
   ```

3. Redeploy the current code with the secret **mounted as an environment variable**,
   adding these two flags to the `gcloud run deploy` command above:

   The main deployment example uses PowerShell. Continue its preceding argument with a
   backtick, then add:

   ```powershell
   --set-secrets=QISKIT_IBM_TOKEN=ibm-quantum-token:latest `
   --update-env-vars="IBM_QUANTUM_INSTANCE=YOUR_INSTANCE_CRN,IBM_QUANTUM_BACKEND=YOUR_BACKEND_NAME"
   ```

   Replace `YOUR_INSTANCE_CRN` and `YOUR_BACKEND_NAME` with the account's values before
   running the command; do not copy those example strings literally. If you leave the
   instance or backend unset, omit `--update-env-vars` or include only the value you are
   setting. Without an instance CRN, backend selection is limited to Open Plan devices.

4. Verify, then record before claiming anything: `GET /api/health` returns
   `{"status":"ok"}`; a new room reports `quantum.enabled` as `true`; the first real
   collapse's `quantum.last.job_id` is saved somewhere durable. Until that job id
   exists, the honest statement is "implemented and tested against a mock, not yet run
   on hardware".

5. To disable it again, redeploy with `--update-env-vars=QCHECKERS_DISABLE_HARDWARE=1`
   (or drop the secret mount).

The key is never sent to the client: `Error` messages carry only the provider exception
*type*, and the `quantum` payload block carries backend and job id but no credential.

## Music and verification

The game uses **Outer Space Loop** by wipics under CC0. The Music toggle is
independent of sound effects, starts playback after a gesture, remembers the user's
choice, and pauses in hidden tabs. Source and license are in `ATTRIBUTION.md`.

Verified locally in this repository (re-run 12 October 2026): **270 Python tests**,
client `npm run typecheck`, client `npm test` (6 checks), and a Next.js production
build. The mocked IBM boundary is exercised by the Python suite; that is **not** evidence
of real hardware behaviour.

Recorded earlier against the hosted demo (needs Playwright + Chromium and network, and
was **not** re-run for this change): public client and audio asset load, live game
creation with WSS state and move exchange, music playback/mute/resume, and seat recovery
after a reload. Treat those as prior observations, not as a fresh result.

```powershell
# Optional Playwright setup (shared with browser_check.py):
python -m pip install playwright
python -m playwright install chromium
python scripts/check_deployment.py
```

See [Cloud Run WebSocket guidance](https://cloud.google.com/run/docs/triggering/websockets)
and [IBM account configuration](https://quantum.cloud.ibm.com/docs/en/guides/initialize-account)
for the provider behavior underlying these settings.
