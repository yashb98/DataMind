"""
JupyterHub Configuration — DataMind Phase 4
Tenant-isolated spawner with resource limits.
Kernel start < 10s SLO.
"""
import os

# ── Authenticator ─────────────────────────────────────────────────────────────
# Use DummyAuthenticator for dev; replace with OAuthenticator for prod
c.JupyterHub.authenticator_class = "dummy"
c.DummyAuthenticator.password = os.environ.get("JUPYTERHUB_ADMIN_PASSWORD", "changeme")

# ── Spawner ───────────────────────────────────────────────────────────────────
c.JupyterHub.spawner_class = "simple"  # SimpleSpawner for dev; DockerSpawner for prod

# Resource limits per kernel (tenant isolation)
c.Spawner.mem_limit = "2G"
c.Spawner.cpu_limit = 2.0

# Pre-spawn hook: inject tenant env vars
def pre_spawn_hook(spawner):
    username = spawner.user.name
    spawner.environment.update({
        "DATAMIND_TENANT_ID": username,
        "DATAMIND_API_URL": os.environ.get("DATAMIND_API_URL", "http://api:8000"),
        "MLFLOW_TRACKING_URI": "http://mlflow:5000",
    })

c.Spawner.pre_spawn_hook = pre_spawn_hook

# ── Database ──────────────────────────────────────────────────────────────────
db_host = os.environ.get("POSTGRES_HOST", "postgres")
db_name = os.environ.get("POSTGRES_DB", "datamind_core")
db_user = os.environ.get("POSTGRES_USER", "datamind")
db_pass = os.environ.get("POSTGRES_PASSWORD", "changeme")
c.JupyterHub.db_url = f"postgresql://{db_user}:{db_pass}@{db_host}/{db_name}"

# ── Hub settings ──────────────────────────────────────────────────────────────
c.JupyterHub.hub_ip = "0.0.0.0"
c.JupyterHub.ip = "0.0.0.0"
c.JupyterHub.port = 8000

# Admin users
c.Authenticator.admin_users = {"admin"}

# Idle culling: shut down kernels idle > 1 hour
c.JupyterHub.services = [
    {
        "name": "idle-culler",
        "command": ["python3", "-m", "jupyterhub_idle_culler", "--timeout=3600"],
        "admin": True,
    }
]

# Allow all users to access their servers
c.JupyterHub.allow_named_servers = True
c.JupyterHub.named_server_limit_per_user = 3

# Cookie secret
c.JupyterHub.cookie_secret_file = "/srv/jupyterhub/jupyterhub_cookie_secret"
