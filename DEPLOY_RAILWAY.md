# Publicar o Energia+ no Railway com Docker

A página inicial e a API são servidas pelo mesmo aplicativo Flask. Você vai criar dois serviços no mesmo projeto Railway. A API terá o domínio HTTPS que você pode compartilhar. O MySQL será acessado pela rede privada.

## 1. Adicione os arquivos ao GitHub

Extraia o conteúdo deste ZIP **na pasta do seu repositório onde está o `app.py`**. Ao final, `Dockerfile`, `railway.json`, `requirements.txt` e `app.py` devem estar lado a lado. Mantenha a pasta `deploy/` que acompanha o ZIP.

| Arquivo novo | Função |
| --- | --- |
| `Dockerfile` | Instala as dependências e inicia a aplicação Flask com Gunicorn em `0.0.0.0`, na porta fornecida pelo Railway. |
| `.dockerignore` | Limita os arquivos enviados ao build e exclui o `.env` local. |
| `railway.json` | Configura o build, a preparação do banco e a verificação de `/api/estados`. |
| `deploy/inicializar_banco.py` | Aplica os scripts originais, na ordem, ao banco indicado por `DB_NAME`. |
| `DEPLOY_RAILWAY.md` | Este passo a passo. |

No terminal do VS Code, dentro do repositório já clonado e conectado ao GitHub, execute

```powershell
git add -- Dockerfile .dockerignore railway.json deploy/inicializar_banco.py DEPLOY_RAILWAY.md
git commit -m "Adiciona deploy do Energia+ com Docker e Railway"
git push
```

O Railway constrói a imagem na nuvem. Você pode fazer o deploy pelo navegador mesmo em um PC sem Docker Desktop.

## 2. Crie os serviços

1. No painel do Railway, abra **New Project → Empty Project**.
2. Dentro do projeto, clique em **+ New → Database → Add MySQL**. Neste guia, o serviço se chama `MySQL`. Aguarde o banco ficar ativo. Para esta instalação, use um banco dedicado ao Energia+.
3. No mesmo projeto, clique em **+ New → GitHub Repo** e selecione o repositório do Energia+ e a branch que recebeu os arquivos. Se o painel pedir acesso ao GitHub, autorize esse repositório.
4. Abra o serviço da aplicação. Quando `app.py` e `Dockerfile` estão na raiz do repositório, mantenha o **Root Directory** padrão. Deixe o **Start Command** com o valor padrão para usar o Gunicorn definido no Dockerfile. Se uma tentativa automática começar antes da configuração das variáveis, conclua a etapa 3 e publique novamente.

## 3. Configure as variáveis da API

No serviço **da aplicação**, abra **Variables → Raw Editor** e adicione estas linhas, preservando outras variáveis que você já use. Se o nome do serviço do banco for diferente de `MySQL`, troque apenas a palavra `MySQL` dentro das referências pelo nome exato mostrado no painel.

```dotenv
DB_HOST=${{MySQL.MYSQLHOST}}
DB_PORT=${{MySQL.MYSQLPORT}}
DB_NAME=${{MySQL.MYSQLDATABASE}}
DB_USER=${{MySQL.MYSQLUSER}}
DB_PASSWORD=${{MySQL.MYSQLPASSWORD}}
COOKIE_SECURE=1
FLASK_DEBUG=0
```

Adicione também uma variável chamada **`SECRET_KEY`**. Para gerar o valor no PowerShell do Windows, execute as três linhas abaixo e copie a sequência exibida para o campo de valor no Railway.

```powershell
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
[Convert]::ToBase64String($bytes)
```

Guarde a chave nas variáveis do serviço e mantenha o mesmo valor nos próximos deploys para preservar as sessões. O Railway fornece `PORT` automaticamente.

## 4. Publique e gere o link

1. Salve as variáveis e clique em **Deploy** ou **Deploy Changes**. Acompanhe a aba **Deployments** do serviço da aplicação.
2. No primeiro deploy, o pré-deploy executa `sql/01_banco_original.sql` e `sql/02_complementos.sql` nessa ordem. O inicializador usa o banco selecionado pela conexão, ajusta em memória os cabeçalhos SQL locais e reconhece as linhas de comentário do segundo arquivo. Ele registra os scripts concluídos em `Energia_Deploy`; em uma nova publicação, cada etapa concluída é pulada. A instalação cria as tabelas, os estados e o catálogo de aparelhos. Os cadastros que você já tenha feito no seu computador continuam no seu MySQL local.
3. Após a preparação do banco, o Railway verifica `/api/estados`. Quando o serviço da aplicação estiver **Active**, abra **Settings → Networking → Public Networking → Generate Domain**. Se houver um campo de porta, selecione a porta em que o Gunicorn iniciou, visível nos logs. Copie o endereço **HTTPS** gerado. Esse é o link para enviar ao professor ou à equipe.

## 5. Confira pelo navegador

| O que abrir | Resultado esperado |
| --- | --- |
| O domínio HTTPS, sem acrescentar um caminho | Tela do Energia+ com as opções **Entrar** e **Cadastrar**. |
| O mesmo domínio seguido de `/api/estados` | Lista JSON de estados lida do MySQL, com `id`, `nome` e `sigla`. No banco novo são dez registros, incluindo São Paulo (`SP`). |
| **Cadastrar** na página inicial e, depois, **Sair → Entrar** | Uma conta de teste criada na nuvem consegue entrar de novo. Esse teste também confirma a gravação no banco e o funcionamento da sessão. |

Se o pré-deploy mostrar **Access denied** ou **Unknown MySQL server host**, confira se as referências apontam para o serviço MySQL do mesmo ambiente e se ele está ativo. Se o log mostrar **Configure SECRET_KEY no arquivo .env**, adicione `SECRET_KEY` nas variáveis da aplicação. Em ambos os casos, aplique as mudanças e refaça o deploy. Se a página apresentar **502**, confira o **Start Command** e se a porta do domínio corresponde à porta que aparece no log do Gunicorn.

## Documentação do Railway

[Build com Dockerfile](https://docs.railway.com/builds/dockerfiles) · [MySQL](https://docs.railway.com/databases/mysql) · [Referências entre serviços](https://docs.railway.com/variables/reference) · [Comando de pré-deploy](https://docs.railway.com/deployments/pre-deploy-command) · [Domínio público](https://docs.railway.com/networking/public-networking)
