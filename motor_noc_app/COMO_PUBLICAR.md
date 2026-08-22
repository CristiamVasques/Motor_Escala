# Como publicar o código no GitHub

Guia passo a passo. Duas rotas: pela **página do GitHub** (mais simples, sem
instalar nada) e pelo **terminal com git** (permite atualizar depois com um
comando).

---

## Antes de começar: o que publicar

**Publique o pacote `motor_noc_app/`.** Ele é autocontido, não tem dados
pessoais nem credenciais, e pesa 240 KB.

**Sobre o texto do TCC:** publicar o `.tex` junto é opcional. A favor, fica tudo
reunido e o trabalho vira reproduzível de ponta a ponta. Contra, você passa a
manter dois lugares em sincronia e expõe versões intermediárias do texto antes da
defesa. Sugestão: publique só o código agora e, depois da aprovação, acrescente o
PDF final numa pasta `docs/`.

**Verificação já feita:** varri o pacote atrás de senhas, tokens, endereços de
e-mail, CPFs e nomes de pessoas reais. Não há nada — os analistas das instâncias
são sintéticos, identificados por código (`A001`, `A002`) e caracterizados apenas
por nível, competências e capacidade.

---

## Rota A — pela página do GitHub (sem instalar nada)

Serve para publicar uma vez. Para atualizar depois, repita o processo ou migre
para a Rota B.

**1.** Entre em [github.com](https://github.com) e faça login. Se ainda não tem
conta, crie uma — é gratuita e repositórios públicos não têm custo.

**2.** Clique no `+` no canto superior direito e escolha **New repository**.

**3.** Preencha:

| Campo | Sugestão |
|---|---|
| Repository name | `motor-escalonamento-noc` |
| Description | Motor algorítmico para escalonamento de analistas em Centros de Operações de Rede — TCC UFABC/TSI 2026 |
| Visibility | **Public** (necessário para citar no TCC) |
| Add a README file | **deixe desmarcado** — já existe um |
| Add .gitignore | **deixe desmarcado** — já existe um |
| Choose a license | **MIT License** (ver seção sobre licença abaixo) |

**4.** Clique em **Create repository**.

**5.** Na página que abrir, clique em **uploading an existing file** (o link no
meio da tela).

**6.** Arraste a pasta `motor_noc_app` inteira para a área indicada. O navegador
sobe a estrutura de subpastas junto.

**7.** No campo de mensagem, escreva algo como `Versão inicial do protótipo` e
clique em **Commit changes**.

Pronto. O endereço será `https://github.com/SEU-USUARIO/motor-escalonamento-noc`.

---

## Rota B — pelo terminal (recomendada se for atualizar o código)

**1. Instale o git**, se ainda não tiver:

- Windows: baixe em [git-scm.com](https://git-scm.com/download/win) e instale
  aceitando os padrões
- macOS: `xcode-select --install`
- Linux: `sudo apt install git`

Confira com `git --version`.

**2. Identifique-se** (só na primeira vez, vale para todos os repositórios):

```bash
git config --global user.name "Cristiam Vasques"
git config --global user.email "seu-email@exemplo.com"
```

Use o mesmo e-mail cadastrado no GitHub, senão os commits não aparecem
associados ao seu perfil.

**3. Crie o repositório vazio no GitHub** seguindo os passos 1 a 4 da Rota A ---
mas **sem** marcar nenhuma das caixas de README, .gitignore ou licença. O
repositório precisa nascer vazio para receber o histórico local.

**4. No terminal, entre na pasta do projeto e inicialize:**

```bash
cd caminho/para/motor_noc_app

git init
git add .
git commit -m "Versão inicial do protótipo"
git branch -M main
git remote add origin https://github.com/SEU-USUARIO/motor-escalonamento-noc.git
git push -u origin main
```

Substitua `SEU-USUARIO` pelo seu nome de usuário no GitHub.

**5. Autenticação.** No `git push`, o GitHub pede login — e **não aceita mais a
senha da conta**. Você precisa de um *Personal Access Token*:

1. No GitHub, clique na sua foto → **Settings**
2. Desça até **Developer settings** (última opção do menu lateral)
3. **Personal access tokens** → **Tokens (classic)** → **Generate new token
   (classic)**
4. Dê um nome (`TCC`), escolha a validade e marque a permissão **repo**
5. Clique em **Generate token** e **copie o token** — ele só aparece uma vez

Quando o terminal pedir a senha, cole o token. Guarde-o num gerenciador de
senhas; se perder, gere outro.

**6. Para atualizar depois de mudar algo:**

```bash
git add .
git commit -m "descrição do que mudou"
git push
```

---

## Sobre a licença

Escolher uma licença importa: sem ela, o padrão legal é que **ninguém pode usar,
copiar ou modificar** seu código, mesmo estando público. Para um trabalho
acadêmico, duas opções razoáveis:

**MIT** — permissiva. Qualquer um pode usar, inclusive comercialmente, desde que
mantenha o aviso de autoria. É a mais comum em código acadêmico e a que menos
atrapalha quem quiser citar ou estender seu trabalho.

**CC BY-NC-SA 4.0** — exige atribuição, proíbe uso comercial e obriga a
compartilhar derivados sob a mesma licença. Mais restritiva; alguns programas de
pós-graduação preferem.

Na dúvida, MIT. Confirme se a UFABC tem política própria sobre licenciamento de
produção acadêmica.

---

## Depois de publicar: ligue o repositório ao TCC

Com o endereço em mãos, vale acrescentá-lo ao trabalho. Duas alterações
pequenas:

**No `apendices.tex`**, no Apêndice C, logo antes da seção de reprodução:

```latex
O código-fonte completo do protótipo está disponível publicamente em
\url{https://github.com/SEU-USUARIO/motor-escalonamento-noc}, sob licença MIT.
```

**No `README.md` do repositório**, acrescente uma linha ligando de volta ao
trabalho, para quem chegar pelo GitHub entender o contexto.

Isso fecha o ciclo de reprodutibilidade que a Seção de Validade do TCC
reivindica: o leitor tem o texto, os comandos e o código.

---

## Problemas comuns

| Sintoma | Causa | Solução |
|---|---|---|
| `fatal: not a git repository` | esqueceu o `git init` | rode `git init` na pasta do projeto |
| `Support for password authentication was removed` | usou a senha da conta | use o Personal Access Token |
| `Updates were rejected` | o repositório remoto não estava vazio | recrie sem README/licença, ou use `git pull --rebase origin main` antes |
| `__pycache__` aparece no GitHub | `.gitignore` não foi versionado | confira que o arquivo `.gitignore` está na raiz do pacote |
| Arquivos de saída no repositório | rodou o motor antes do `git add` | `git rm -r --cached saida/` e commite de novo |
