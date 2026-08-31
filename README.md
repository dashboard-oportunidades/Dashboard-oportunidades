# Monitor de bases de duche — leroymerlin.pt

Corres manualmente a partir do teu PC sempre que quiseres atualizar, lê as
listagens de bases de duche e avisa-te por **email** e por **notificação no
telemóvel** quando aparece alguma abaixo do preço que definiste — ou quando
uma que já conhecias baixa.

**Porque não corre sozinho na nuvem:** a Leroy Merlin tem proteção anti-bot
(Datadome) que bloqueia com 403 os pedidos vindos de servidores do GitHub
Actions — e provavelmente de qualquer outra nuvem. A partir de uma ligação de
casa normal não há esse problema, por isso o script corre localmente e depois
publica o resultado no GitHub.

Custo: zero — só precisas do teu PC ligado no momento em que corres o script.

---

## 1. Preparar o repositório localmente

1. Clona o repositório para o teu PC.
2. Instala o Python (3.10+) se ainda não tiveres.
3. Instala as dependências:
   ```bash
   pip install -r requirements.txt
   ```
4. Copia `.env.example` para `.env` e preenche os valores (ver secções 4 e 5).
   O `.env` fica só no teu PC — está no `.gitignore`, nunca é enviado para o GitHub.

## 2. Escolher o que queres vigiar

Abre o `config.json` e ajusta:

| Campo | O que faz |
|---|---|
| `max_price` | O limite. Só és avisado abaixo deste valor. |
| `listing_urls` | As páginas de listagem a percorrer. |
| `max_pages` | Quantas páginas seguir em cada listagem. |
| `include_keywords` | O nome tem de conter pelo menos uma destas palavras. |
| `exclude_keywords` | Descarta resguardos, torneiras e outra tralha que aparece na categoria. |

**Dica importante para os URLs:** vai ao site, aplica os filtros que quiseres
(medidas, cor, preço máximo, "Vendido por Leroy Merlin", ordenar por preço
ascendente) e copia o URL da barra de endereço. Os filtros ficam no URL, por
isso quanto melhor filtrares no browser, menos páginas o script tem de ler.
Ordenar por preço ascendente é o truque mais útil: as mais baratas ficam todas
na primeira página e podes pôr `max_pages` a 2.

Testa localmente antes de publicar:

```bash
pip install -r requirements.txt
python monitor.py --dry-run
```

O `--dry-run` mostra o que teria enviado, sem enviar nada.

## 3. Capturar o cookie da loja

Esta é a única parte chata, mas só se faz uma vez (uns 2 minutos por loja).

A Leroy Merlin guarda a loja escolhida num **cookie**, não no URL — por isso
não há forma de pedir "preços de Alfragide" só com um link. O script resolve
isto fazendo uma passagem por loja, cada uma com o seu cookie.

Para cada loja que quiseres vigiar:

1. Abre o site num separador anónimo e escolhe essa loja em **"Escolher a minha loja"**.
2. Abre as Ferramentas de Programador (F12, ou Cmd+Option+I no Mac).
3. Vai a **Application → Cookies → https://www.leroymerlin.pt** (no Firefox é
   **Storage → Cookies**).
4. Procura o cookie cujo valor mudou ao escolheres a loja — tipicamente tem
   "store", "pos" ou "shop" no nome, e um valor curto como `041`.
   Truque para o encontrares depressa: repete o processo com duas lojas
   diferentes e vê qual é o cookie que muda de valor.
5. Copia o nome e o valor para o `config.json`, no bloco dessa loja.

Não te consigo dar o nome exato do cookie daqui — não é visível do lado do
servidor e a Leroy Merlin muda estas coisas de tempos a tempos. Por isso o
script aceita qualquer nome de cookie, e o `config.json` já traz as oito lojas
preparadas:

| Região | Lojas |
|---|---|
| Lisboa | Alta de Lisboa, Colombo, Alfragide, Sacavém, Oeiras |
| Faro | Loulé, Albufeira, Portimão |

Não há loja em Faro cidade — as três do distrito são Loulé (Av. do Algarve),
Albufeira (EN125, na Guia) e Portimão (Chão das Donas). Na zona de Lisboa podes
acrescentar Amadora, Loures, Almada, Carcavelos ou Cascais da mesma forma.

**As lojas com `cookies` vazio são simplesmente saltadas.** Podes arrancar com
uma ou duas e ir acrescentando as outras quando te apetecer, sem partir nada.
Nos avisos, cada preço aparece com a região ao lado (`Loulé (Faro): 59,90 €`)
para veres logo se a mais barata está ao virar da esquina ou a 300 km.

Se o cookie deixar de funcionar, o script deteta que todas as lojas devolveram
exatamente os mesmos preços e escreve um aviso no log — não ficas a pensar que
os preços são iguais quando na verdade a loja não pegou.

### O que varia e o que não varia

Só os produtos **vendidos pela Leroy Merlin** têm preço por loja. Os do
Marketplace (Baño Total, BELLOBATH, NALA e afins) são preço nacional e
aparecem sempre iguais — o script identifica-os e marca-os como tal no aviso.
Se só te interessarem os da própria Leroy Merlin, põe `"skip_marketplace": true`
no `config.json`. Compensa: são esses que podes levantar em loja no próprio dia.

## 4. Notificações no telemóvel (ntfy)

O [ntfy.sh](https://ntfy.sh) é gratuito e não precisa de conta:

1. Instala a app **ntfy** (App Store / Play Store).
2. Inventa um nome de tópico difícil de adivinhar, por exemplo
   `bases-duche-4f9q2x`. Quem souber o nome consegue ver as mensagens, por isso
   não uses `bases-duche`.
3. Na app, subscreve esse tópico.

## 5. Email

Com Gmail precisas de uma *palavra-passe de aplicação* (não a tua password
normal): ativa a verificação em dois passos e depois cria uma em
myaccount.google.com → Segurança → Palavras-passe de aplicações.

- `SMTP_HOST`: `smtp.gmail.com`
- `SMTP_PORT`: `465`
- `SMTP_USER`: o teu endereço
- `SMTP_PASS`: a palavra-passe de aplicação

## 6. Preencher o `.env`

Abre o `.env` que criaste no passo 1 e preenche `SMTP_USER`, `SMTP_PASS`,
`MAIL_TO` e `NTFY_TOPIC` com os valores das secções 4 e 5. O limite de preço
não vem daqui — continua a ser o `max_price` do `config.json`.

## 7. Publicar a página no telemóvel

O repositório traz uma pasta `docs/` com uma página que mostra os preços por
loja e a evolução ao longo do tempo. Para a pores no ar:

1. No repositório: **Settings → Pages**.
2. Em *Source*, escolhe **Deploy from a branch**.
3. Branch: `main`, pasta: **/docs**. Guarda.
4. Passado um minuto tens o endereço: `https://<o-teu-utilizador>.github.io/<o-repo>/`

**Se o repositório for privado**, o GitHub Pages exige um plano pago. Nesse
caso torna o repositório público — não há aqui nada sensível, porque as
palavras-passe ficam todas em *Secrets*, que nunca são públicos.

### Adicionar ao ecrã principal

- **iPhone:** abre o endereço no Safari (tem de ser o Safari) → botão de
  partilha → *Adicionar ao ecrã principal*.
- **Android:** abre no Chrome → menu dos três pontos → *Adicionar ao ecrã
  principal*.

Fica com ícone próprio e abre em ecrã inteiro, sem barra de endereço.

### O que a página faz

- **A linha de água** atravessa a lista à altura do teu limite. O que está
  abaixo fica submerso; o que está acima fica em seco.
- **Arrasta o cursor** para mover o limite e ver o que entra e sai. Isto é só
  no teu telemóvel — não muda o valor a que és alertado, que continua a ser o
  `max_price` do `config.json`.
- **Filtra por região** para veres só Lisboa ou só Faro.
- **A linha por baixo de cada preço** é a evolução dos últimos meses. Só
  aparece quando o preço mudou alguma vez; fica verde quando desceu.
- Toca numa base de duche para abrir a página do produto no site.

## 8. Arrancar e atualizar

Sempre que quiseres verificar os preços, corre no PowerShell, na pasta do
repositório:

```powershell
./atualizar.ps1
```

Isto carrega o `.env`, corre o `monitor.py`, e se houver preços novos faz
commit e push de `state.json` e `docs/data.json` automaticamente. A primeira
corrida cria o `docs/data.json` e enche a página — até lá ela mostra apenas
instruções, e vais receber um aviso com *tudo* o que está abaixo do limite. A
partir daí só recebes novidades e descidas de preço.

---

## Como funciona

- A página é estática: o `atualizar.ps1` escreve o `docs/data.json` e faz
  commit/push a partir do teu PC; o GitHub Pages serve o ficheiro. Não há
  servidor a correr nem nada a pagar.
- O `state.json` guarda o último preço visto de cada produto **em cada loja** e é gravado de
  volta no repositório em cada corrida. É por isso que não recebes o mesmo
  aviso todos os dias — e ao fim de uns meses tens um histórico de preços no
  histórico de commits.
- Os produtos são identificados pelo ID no fim do URL, não pelo nome, por isso
  aguenta mudanças de título.
- Se o site mudar de estrutura e o script deixar de extrair produtos, ele
  termina com erro e o `atualizar.ps1` não faz commit nenhum — ficas a saber
  pelo próprio terminal em vez de assumires silenciosamente que não há
  promoções.

## Boa vizinhança

Um `delay_seconds` de 3 segundos entre páginas é tráfego irrelevante para
o site, mesmo multiplicado por doze lojas. Se acrescentares muitas mais lojas,
aumenta o `delay_seconds` em vez de o baixar, e evita correr o script muitas
vezes seguidas no mesmo dia — além de ser má prática, arriscas ser bloqueado.
Confirma também os
[Termos e Condições](https://www.leroymerlin.pt/politicas-e-condicoes/termos-e-condicoes-gerais/)
do site, e usa isto só para uso pessoal.
