"""CLI AI handler — autenticação via OAuth de assinatura (Claude Code / Codex CLI).

Em vez de chamar a API do provider via API key (pay-per-token, como o
``LiteLLMAIHandler`` default), este handler dirige um *CLI de assinatura* em modo
headless — ex.: ``claude -p`` (Claude Max) ou ``codex exec`` (ChatGPT Pro). Esses
CLIs autenticam pela sessão OAuth da assinatura, então a revisão roda na cota da
assinatura — **sem API key e sem a cota do GitHub Copilot**.

Requisito: o CLI precisa estar autenticado no ambiente onde o PR-Agent roda
(máquina local ou self-hosted runner já logado). Runners cloud padrão
(GitHub-hosted) não têm sessão de assinatura — use local/self-hosted.

Seleção: defina ``[config] ai_handler="cli"`` (default ``"litellm"``) e configure
a seção ``[cli_ai]`` em ``configuration.toml``.
"""
import asyncio
import shlex

from pr_agent.algo.ai_handlers.base_ai_handler import BaseAiHandler
from pr_agent.config_loader import get_settings
from pr_agent.log import get_logger


class CliAiHandler(BaseAiHandler):
    """Dirige um CLI de assinatura (OAuth) em headless como provider de LLM."""

    def __init__(self):
        settings = get_settings()
        # Comando do CLI da assinatura. Ex.: "claude -p"  ou  "codex exec".
        self.command = settings.get("CLI_AI.COMMAND", "claude -p")
        self.timeout = int(settings.get("CLI_AI.TIMEOUT_SECONDS", 300))
        # Como entregar o prompt ao CLI: "stdin" (default, seguro p/ diffs grandes)
        # ou "arg" (anexa o prompt como último argumento do comando).
        self.pass_prompt_via = str(
            settings.get("CLI_AI.PASS_PROMPT_VIA", "stdin")
        ).lower()

    @property
    def deployment_id(self):
        return None

    async def chat_completion(self, model: str, system: str, user: str,
                              temperature: float = 0.2, img_path: str = None):
        if img_path:
            get_logger().warning(
                "CliAiHandler: img_path ignorado (não suportado via CLI).")

        prompt = f"{system}\n\n{user}" if system else user
        argv = shlex.split(self.command)
        get_logger().info(
            f"CliAiHandler: executando '{self.command}' "
            f"(param model='{model}' ignorado — o CLI usa o modelo da assinatura)")

        try:
            if self.pass_prompt_via == "arg":
                proc = await asyncio.create_subprocess_exec(
                    *argv, prompt,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout)
            else:
                proc = await asyncio.create_subprocess_exec(
                    *argv,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(prompt.encode()), timeout=self.timeout)
        except asyncio.TimeoutError as e:
            raise TimeoutError(
                f"CliAiHandler: '{self.command}' excedeu {self.timeout}s") from e

        if proc.returncode != 0:
            err = stderr.decode(errors="replace")[:800]
            raise RuntimeError(
                f"CliAiHandler: '{self.command}' falhou (rc={proc.returncode}). "
                f"O CLI está autenticado neste ambiente? stderr: {err}")

        resp = stdout.decode(errors="replace").strip()
        if not resp:
            err = stderr.decode(errors="replace")[:400]
            raise RuntimeError(
                f"CliAiHandler: resposta vazia de '{self.command}'. stderr: {err}")

        # O CLI não expõe finish_reason; usamos "stop" (resposta completa).
        return resp, "stop"
