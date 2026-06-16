# Modo OAuth/CLI de assinatura (Claude Code / Codex) — sem API key

Este fork adiciona um **AI handler** que roda a revisão de PR na **cota da sua
assinatura de chat/CLI** (Claude Max via `claude` CLI, ChatGPT Pro via `codex`
CLI), em vez de uma **API key** (pay-per-token). Resolve o caso de quem **só tem
assinatura** (sem cota de API) e/ou esbarrou na **cota do GitHub Copilot**.

## Por quê

O PR-Agent original consome o LLM via **API key** (`litellm` → API OpenAI/Anthropic).
Uma **assinatura de chat/CLI** é **OAuth**, não API — alimenta os apps e os
clientes de terminal, mas **não expõe API key**. A única forma de aproveitar a
assinatura é **dirigir o CLI logado** em modo headless.

## Como funciona

`CliAiHandler` (`pr_agent/algo/ai_handlers/cli_ai_handler.py`) implementa a
interface `BaseAiHandler.chat_completion(...)` rodando o CLI como subprocess: o
prompt (system + user que o PR-Agent já monta) vai por `stdin`, e a resposta é o
`stdout`. **Todo o resto do pipeline do PR-Agent é reaproveitado** — representação
de diff em hunks, prompts, post inline via Reviews API, review incremental.

```
trigger → diff em hunks → prompt (.toml) → CliAiHandler → claude -p / codex exec
        → resposta → parse → post inline (Reviews API)
```

## Como ativar

Em `configuration.toml` (ou no `.pr_agent.toml` do seu repo):

```toml
[config]
ai_handler = "cli"          # default é "litellm" (API key)

[cli_ai]
command = "claude -p"       # ou "codex exec"
timeout_seconds = 300
pass_prompt_via = "stdin"   # ou "arg"
```

Depois rode normalmente (ex.: `python -m pr_agent.cli --pr_url <URL> review`).

## Onde roda — a auth da assinatura precisa estar no ambiente

O `claude`/`codex` autenticam pela **sessão OAuth** da assinatura. Ela precisa
estar disponível onde o PR-Agent roda. Há dois cenários — **inclusive CI na
nuvem**:

### Local / self-hosted runner
✅ Direto — basta o CLI estar logado (`claude` / `codex login`).

### GitHub-hosted runner (CI na nuvem) — ✅ com o token da assinatura como *secret*
Não há sessão por default, mas você **injeta a credencial via secret**; o handler
é o mesmo, só o **workflow** muda (instala o CLI + fornece a auth):

- **Claude Code (mecanismo oficial para CI)**: gere um token OAuth de longa
  duração com `claude setup-token` (atrelado à assinatura Max) e guarde como
  secret (ex.: `CLAUDE_CODE_OAUTH_TOKEN`). O `claude` lê esse env var e roda na
  assinatura no runner GitHub-hosted. *(Confirme o nome exato do comando/env var
  na doc atual do Claude Code.)*
- **Codex (ChatGPT Pro)**: restaure a credencial do `codex login`
  (ex.: `~/.codex/auth.json`) a partir de um secret antes de rodar. Funciona, mas
  é menos oficial que o `setup-token` do Claude.

### Caveats da auth em CI
- **Ciclo do token**: o token de CI expira / pode ser revogado → rotacione o secret.
- **ToS**: o `claude setup-token` é oferecido pela Anthropic para automação/CI
  (uso previsto). Para **Codex/ChatGPT Pro**, uso headless em CI é zona mais
  cinzenta — verifique os termos da OpenAI antes.
- **Segurança**: o token **é a sua conta** — trate o secret com cuidado (escopo,
  quem tem acesso ao repo).

## Limitações conhecidas

- **Saída estruturada**: os prompts pedem YAML/JSON; o CLI produz, mas sem o
  `response_format` da API — pode exigir prompts mais firmes / parsing robusto.
- **`model`** é ignorado (o CLI usa o modelo da assinatura); a contagem de tokens
  (`tiktoken`) vira aproximação para a compressão de diff.
- **Latência**: há custo de startup do CLI por chamada.

> Status: handler de integração. A viabilidade ponta-a-ponta (qualidade da saída
> estruturada via CLI) deve ser validada num PR real antes de uso em produção.
