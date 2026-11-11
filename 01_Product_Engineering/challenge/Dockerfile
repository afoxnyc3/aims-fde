# A plain, readable Dockerfile. Not the smallest possible image, not the
# cleverest. You should be able to read every line and say what it does.

FROM python:3.12-slim

# uv installs dependencies fast and is already how we run things locally.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

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

COPY llm.py app.py schema.py onboarding.py standard_v02.py demo_standard.json ./
COPY corpus.py retrieval.py qa.py qa_schema.py standard_v0_1.md mcp_server.py ./

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

EXPOSE 7860

# The API key is NOT baked into this image. It arrives at runtime via
# environment variable. Never COPY a .env file into a container image --
# anyone who can pull the image can read it.
# Way 2 (TC5): the same capability as an MCP server on stdio, in the same image:
#   docker run -i --rm -v ".../use_case/data:/data:ro" -e CORPUS_PATH=/data/synthetic_v1.jsonl \
#     -e MCP_PRELOAD=1 -e MCP_AUDIT_LOG=/tmp/mcp_audit.jsonl --env-file ../../.env <image> python mcp_server.py
CMD ["python", "app.py"]
