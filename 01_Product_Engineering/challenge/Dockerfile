# A plain, readable Dockerfile. Not the smallest possible image, not the
# cleverest. You should be able to read every line and say what it does.

# Tag plus digest: the tag says what this is, the digest makes it the same image on
# every build. To move it: docker buildx imagetools inspect python:3.12-slim
FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b

# uv installs dependencies fast and is already how we run things locally.
# Pinned for the same reason as the base image; `latest` is a different uv next month.
COPY --from=ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d /uv /usr/local/bin/uv

WORKDIR /app

# Copy the dependency manifests first. Docker caches layers, so dependencies
# only reinstall when these change -- not on every code edit.
COPY pyproject.toml uv.lock ./

# Install from the LOCK, not from pyproject.toml. pyproject says "gradio>=6.0",
# which resolves to whatever is newest on the day you build -- so an image built
# today and one built next month are different applications wearing the same
# tag. The lock pins every package, including the ones you never asked for.
RUN uv export --frozen --no-dev --no-emit-project -o requirements.txt \
 && uv pip install --system --no-cache -r requirements.txt

COPY llm.py app.py schema.py models.py onboarding.py standard_v02.py demo_standard.json ./
COPY corpus.py retrieval.py qa.py qa_schema.py outcheck.py standard_v0_1.md mcp_server.py ./
# TC6: the input rail and its NeMo config. qa.py calls it before the model on every question.
COPY inputrail.py ./
COPY guardrails/ ./guardrails/

# The ticket corpus is NOT copied in: use_case/data/ is gitignored, and an image
# carries whatever is baked into it to everyone who can pull it. Mount it
# read-only at runtime instead:
#   docker run -v "$PWD/../../use_case/data:/data:ro" \
#     -e CORPUS_PATH=/data/synthetic_v1.jsonl --env-file .env ...
# Without the mount the question endpoint says so; onboarding still works.
# The private role-matrix standard is NOT copied in either. To use it, mount it the
# same way and point at it:
#   -v /path/to/standard_dir:/standard:ro -e ONBOARDING_STANDARD=/standard/<file>.yaml
# or pick a version from the folder (0.5 by default; TC4 runs pin 0.3):
#   -v /path/to/standard_dir:/standard:ro -e ONBOARDING_STANDARD_DIR=/standard -e ONBOARDING_STANDARD_VERSION=0.5
# Without the variable, onboarding uses demo_standard.json.
COPY frontend/ ./frontend/

# Don't run as root. Your security review will ask about this.
RUN useradd --create-home appuser
USER appuser

# app.py binds loopback unless told otherwise. Inside a container that is unreachable
# from the host, so bind all interfaces here and limit exposure where the port is
# published: docker run -p 127.0.0.1:7860:7860 ...
ENV GRADIO_SERVER_NAME=0.0.0.0
EXPOSE 7860

# The API key is NOT baked into this image. It arrives at runtime via
# environment variable. Never COPY a .env file into a container image --
# anyone who can pull the image can read it.
# Way 2 (TC5): the same capability as an MCP server on stdio, in the same image:
#   docker run -i --rm -v ".../use_case/data:/data:ro" -e CORPUS_PATH=/data/synthetic_v1.jsonl \
#     -e MCP_PRELOAD=1 -e MCP_AUDIT_LOG=/tmp/mcp_audit.jsonl --env-file ../../.env <image> python mcp_server.py
CMD ["python", "app.py"]
