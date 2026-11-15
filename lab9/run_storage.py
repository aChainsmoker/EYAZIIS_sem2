import os
import subprocess
from src.config import CONFIG, ROOT

def main():
    db = CONFIG["database"]
    s3 = CONFIG["s3"]
    env = dict(os.environ, POSTGRES_USER=db["user"], POSTGRES_PASSWORD=db["password"], POSTGRES_DB=db["name"], MINIO_USER=s3["access_key"], MINIO_PASSWORD=s3["secret_key"])
    subprocess.run(["docker", "compose", "-p", "eyaziis_sem2_lab9", "up", "-d"], cwd=ROOT, env=env, check=True)

if __name__ == "__main__":
    main()
