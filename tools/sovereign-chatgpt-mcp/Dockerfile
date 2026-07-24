FROM node:22-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ANDROID_SDK_ROOT=/opt/android-sdk \
    SOVEREIGN_ANDROID_NATIVE_BUILD_MODE=github_actions \
    PATH=/opt/venv/bin:/opt/android-sdk/platform-tools:/opt/android-sdk/cmdline-tools/latest/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       file \
       git \
       jq \
       python3 \
       python3-pip \
       python3-venv \
       unzip \
       zip \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && corepack enable

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY policy.py runtime.py database.py database_evidence_tools.py command_contract.py command_queue.py broker_client.py owner_input_client.py a2a_runtime_client.py document_pipeline.py github_knowledge_canary.py github_issue_contracts.py owner_input_widget.py self_heal.py android_hardening.py android_validation_router.py mcp_protocol_health.py sovereign_cognitive_widget.py server.py tool_extensions.py llm_boundary_contract.py repository_skill_tools.py proven_learning_tools.py skill_supply_chain_tools.py deterministic_contract.py deterministic_architecture_tools.py enterprise_backend_tools.py freemium_product_architect_tools.py openai_project_access_tools.py operating_profile.py operational_governance_tools.py operational_assurance_tools.py output_contracts.py toolchain_composition.py patchmon_operator.py launcher.py /app/
COPY config /app/config
COPY skills /app/skills

RUN useradd --create-home --uid 10001 sovereign \
    && mkdir -p /opt/sovereign-chatgpt-tools/workspaces /opt/android-sdk \
    && chown -R sovereign:sovereign /app /opt/sovereign-chatgpt-tools /opt/android-sdk

USER sovereign
EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=8s --start-period=15s --retries=3 \
  CMD python /app/mcp_protocol_health.py --url http://127.0.0.1:8090/mcp --timeout-seconds 5 || exit 1

CMD ["python", "launcher.py"]
