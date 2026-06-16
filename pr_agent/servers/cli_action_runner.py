"""GitHub Action entrypoint para o handler CLI/OAuth (fork).

Wrapper fino sobre ``github_action_runner.run_action()``: seleciona o
``CliAiHandler`` e o configura a partir de variáveis de ambiente definidas pelo
``action.yml``, e então roda o fluxo padrão de Action do PR-Agent (lê o PR do
evento e posta a revisão). Faz a revisão rodar numa **assinatura de chat/CLI**
(Claude Code / Codex) em vez de uma API key.

Variáveis de ambiente lidas (definidas pelo action.yml):
- ``PR_AGENT_AI_HANDLER``       (default "cli")
- ``PR_AGENT_CLI_COMMAND``      (default "claude -p")
- ``PR_AGENT_CLI_TIMEOUT``      (default "300")
- ``PR_AGENT_CLI_PASS_PROMPT_VIA`` (default "stdin")

Auth da assinatura (ex.: ``CLAUDE_CODE_OAUTH_TOKEN``) é lida pelo próprio CLI —
o action.yml a exporta no ambiente.
"""
import asyncio
import os

from pr_agent.config_loader import get_settings
from pr_agent.servers.github_action_runner import run_action


def _configure_cli_handler() -> None:
    settings = get_settings()
    settings.set("CONFIG.AI_HANDLER",
                 os.environ.get("PR_AGENT_AI_HANDLER", "cli"))
    settings.set("CLI_AI.COMMAND",
                 os.environ.get("PR_AGENT_CLI_COMMAND", "claude -p"))
    settings.set("CLI_AI.TIMEOUT_SECONDS",
                 os.environ.get("PR_AGENT_CLI_TIMEOUT", "300"))
    settings.set("CLI_AI.PASS_PROMPT_VIA",
                 os.environ.get("PR_AGENT_CLI_PASS_PROMPT_VIA", "stdin"))


def main() -> None:
    _configure_cli_handler()
    asyncio.run(run_action())


if __name__ == "__main__":
    main()
