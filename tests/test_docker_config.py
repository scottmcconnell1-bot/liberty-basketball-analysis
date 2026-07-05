"""Stage 9C Docker configuration sanity checks (no Docker daemon required)."""

import os


def test_dockerfile_declares_port_and_entrypoint():
    dockerfile = open(
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "Dockerfile"),
        encoding="utf-8",
    ).read()
    assert "EXPOSE 8080" in dockerfile
    assert 'CMD ["python", "app.py"]' in dockerfile
    assert "requirements.docker.txt" in dockerfile


def test_compose_binds_port_and_persists_state():
    compose_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docker-compose.yml")
    compose = open(compose_path, encoding="utf-8").read()
    assert '"8080:8080"' in compose
    assert "film_analysis.db" in compose
    assert "./uploads:/app/uploads" in compose
    assert 'LIBERTY_DEBUG: "0"' in compose


def test_docker_production_smoke_script_exists():
    script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "docker_production_smoke.sh")
    assert os.path.isfile(script)
    content = open(script, encoding="utf-8").read()
    assert "smoke_test.sh" in content
    assert "docker compose" in content
