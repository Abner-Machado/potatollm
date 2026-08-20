# lowrambench — fundamento

Documento de decisao. Escrito ANTES do codigo. Quem for implementar le isto primeiro
e nao inventa escopo fora daqui.

## 1. A pergunta que a ferramenta responde

Uma so:

> "Esse modelo de IA roda na minha maquina fraca — e a que velocidade?"

Publico: quem roda LLM local em **CPU, sem GPU, com pouca RAM**, no Windows.
Nao e para quem tem placa de video. Ja existe ferramenta para esses.

## 2. O problema e real (evidencia medida, nao suposicao)

Medido em 20/08/2026 numa maquina i3-1215U, 7,7 GB de RAM, sem GPU:

| modelo | resultado |
|---|---|
| qwen3-abliterated **8b** (5,0 GB) | **nao completou** 120 tokens em 10 minutos. RAM livre caiu a 0,07 GB, pagefile inchou a 9,5 GB |
| qwen3-abliterated **4b** (2,5 GB) | 7,48 tok/s, estavel, 17s |

O Ollama deixa baixar 5 GB para descobrir isso sozinho, depois. Nao avisa antes,
nao avisa durante, e o sintoma (maquina travada) nao aponta para a causa.

## 3. Por que nao morre como os concorrentes

Concorrentes verificados na API do GitHub em 20/08/2026:

| repo | stars | foco |
|---|---|---|
| herczy/gguf-estimator | 0 | estimativa de memoria GGUF |
| dlsniper/gguf-llm-vram-calculator | 2 | VRAM |
| GPUforLLM/llm-vram-calculator | 3 | VRAM |
| click6067-ship-it/fitllm-engine | 8 | "fit your GPU or Mac" |

Todos **estimam**, e todos miram **GPU/VRAM**. Nenhum cobre CPU-only com RAM curta.

Decisao central: **a ferramenta MEDE, nao estima.**
Formula se copia numa tarde. Dado acumulado, nao.
Estimativa aqui e so triagem; o produto e a evidencia.

## 4. A contradicao, e como se resolve

Medir exige baixar. A promessa era avisar ANTES de baixar. Solucao em dois estagios:

1. **check** — sem baixar nada: le RAM real da maquina e o tamanho/quantizacao do modelo,
   classifica em `cabe folgado` / `cabe apertado` / `vai paginar` / `nao tente`,
   e sugere o menor equivalente quando o veredito e ruim.
2. **bench** — so depois do OK do usuario: roda de verdade e mede.

Promessa honesta: *"evito o download obviamente ruim; quando voce decidir testar, eu meco de verdade."*

## 5. O vetor e a TABELA, nao a CLI

Ninguem compartilha "instalei uma CLI". Compartilha-se
"tabela de tok/s reais de 15 modelos numa maquina de 8 GB sem GPU".

- O README **abre com a tabela**, nao com instrucao de instalacao.
- O repo **nasce com dado dentro** (10 a 15 medicoes reais). Repo vazio pedindo
  contribuicao nao recebe contribuicao.
- Contribuicao de terceiro entra por Pull Request de um arquivo JSON.

**Trava obrigatoria:** o JSON e SEMPRE gerado pela CLI, com schema fixo e prompt fixo.
Nunca escrito a mao. Sem isso a tabela vira anedota e perde a unica coisa que a torna
valiosa: ser comparavel. Campo nao detectado vira `"unknown"` explicito — nunca chute.

## 6. Instalacao — restricao de projeto, nao detalhe

O usuario-alvo roda Ollama no Windows. **Ollama nao instala Python nem Node.**
Se a instalacao pedir ambiente, metade desiste antes de ver valor.

Regras duras:
- **Arquivo unico**, Python **3.9+**, **somente biblioteca padrao**. Zero dependencia externa.
- Sem virtualenv, sem `requirements.txt`, sem passo de build.
- Windows: um `.cmd` que roda com duplo clique.
- Tem que funcionar baixando um arquivo e rodando.

## 7. Escopo da v1

**FAZ:**
- `check <modelo>` — veredito sem baixar
- `bench <modelo>` — mede tok/s reais, RAM livre no pico, pagefile no pico, se paginou
- `selftest` — ping/diagnostico da propria cadeia (ver secao 8)
- grava JSON com schema fixo, gerado so pela CLI
- `table` — converte os JSON em linha de tabela Markdown

**NAO FAZ na v1:**
qualidade de resposta, perplexity, GPU, varios backends (so Ollama),
interface grafica, servidor, ranking global, upload automatico,
e nao aceita resultado editado a mao como fonte da tabela.

## 8. selftest (exigencia do dono)

Um comando que prova que a cadeia inteira esta viva, sem depender de baixar modelo:
- Python e versao ok
- consegue ler RAM/pagefile nesta plataforma
- servidor Ollama responde (ping na API) — e diz claramente quando NAO responde
- consegue escrever JSON e reconverter em linha de tabela
Saida legivel, e codigo de saida 0 so se tudo passou.

## 9. Teste que prova que a v1 funcionou

Um so, verificavel: rodar `bench` contra um modelo pequeno, gerar o JSON,
rodar `table`, e a tabela ganhar **exatamente uma linha nova derivada daquele JSON**,
sem nenhuma edicao manual.

## 10. Licenca e autoria

MIT. Autoria do dono do repo. Nenhuma mencao a IA, Claude, Anthropic ou assistente
em codigo, README, commit ou release.
