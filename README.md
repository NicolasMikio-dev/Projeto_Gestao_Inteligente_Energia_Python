# Energia+ — Gestão Inteligente de Energia

Protótipo acadêmico com API **Python/Flask**, banco **MySQL** e interface HTML/CSS/JavaScript. Permite cadastrar unidades consumidoras, cômodos e aparelhos, simular consumo, receber leituras de sensores, registrar geração renovável e acompanhar metas e projeções.

## Base desta documentação

Código conferido em 03/11/2026, no commit [3aba6b1 — complementos bd atualizado](https://github.com/NicolasMikio-dev/Projeto_Gestao_Inteligente_Energia_Python/commit/3aba6b18b362d3d2a9b20396048e83540eb8b95a), de 19/10/2026. Esse commit alterou apenas `Consumo_Aparelho.Data_Hora`, de `DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6)` para `DATETIME DEFAULT CURRENT_TIMESTAMP`.

O [guia de instalação existente](GUIA_DE_INSTALACAO.txt) já contém instruções e uma lista de endpoints. Este README complementa esse material sem modificar o código ou os scripts.

**Verificação:** análise estática de código e SQL; não foi executado teste integrado com MySQL nesta revisão. Os resultados dos testes abaixo são expectativas derivadas da implementação.

## Estrutura e requisitos

| Caminho | Função |
|---|---|
| [app.py](app.py) | Rotas Flask, autenticação, SQL e regras de negócio |
| [requirements.txt](requirements.txt) | Flask >=3.1,<4; mysql-connector-python >=9,<11; python-dotenv >=1,<2 |
| [.env.example](.env.example) | Modelo de configuração |
| [sql/01_banco_original.sql](sql/01_banco_original.sql) | Criação do banco e 10 tabelas originais |
| [sql/02_complementos.sql](sql/02_complementos.sql) | 10 tabelas adicionais e cargas de estados/catálogo |
| [templates/index.html](templates/index.html) | Interface servida pelo Flask |
| [static/app.js](static/app.js) | Chamadas à API e atualização do painel |
| documentos_txt/ | Cópias de referência; algumas divergem dos arquivos executáveis |

O guia indica **Python 3.11+ e MySQL Server 8.x**. Não há matriz de versões testadas nem arquivo com versões exatas de todas as dependências. Não é necessário Java, Maven ou Node.js para executar a aplicação.

## Configurar o MySQL

1. Inicie o MySQL Server e conecte-se pelo Workbench ou cliente MySQL.
2. **Para banco novo**, execute integralmente, nesta ordem:
   - `sql/01_banco_original.sql`
   - `sql/02_complementos.sql`
3. Confirme o esquema:

```sql
USE gestao_inteligente_de_energia;
SHOW TABLES;
SELECT ID_Estado, Nome, Sigla FROM Estado;
SELECT ID_Tipo, Nome, Potencia_Referencia_W FROM Aparelho_Catalogo;
```

São esperadas **20 tabelas**, além de 10 estados/DF e 16 tipos de aparelhos na instalação nova. Não há carga inicial de usuários: crie uma conta pela interface ou API.

**Banco existente:** não reaplique os scripts indiscriminadamente. O script 01 usa `CREATE DATABASE` e `CREATE TABLE` sem `IF NOT EXISTS`; o 02 também cria `Credencial` sem essa proteção. As demais criações com `IF NOT EXISTS` não atualizam estruturas antigas. Compare o esquema existente antes de executar trechos faltantes. Não há migrações versionadas para atualizar instalações anteriores.

Os scripts fixam o nome `gestao_inteligente_de_energia`. Alterar apenas `DB_NAME` não renomeia nem cria o banco. O usuário usado para instalar o esquema precisa de permissões de criação; a aplicação precisa de leitura e escrita nas tabelas utilizadas. O repositório não fornece script de criação de usuário MySQL ou de concessão de permissões.

## Executar no Windows / PowerShell

Com Git e Python instalados:

```powershell
git clone https://github.com/NicolasMikio-dev/Projeto_Gestao_Inteligente_Energia_Python.git
cd Projeto_Gestao_Inteligente_Energia_Python
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

Copie o valor gerado para `SECRET_KEY` e edite o `.env` com suas credenciais:

```dotenv
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=gestao_inteligente_de_energia
DB_USER=root
DB_PASSWORD=SUA_SENHA_DO_MYSQL
SECRET_KEY=COLE_A_CHAVE_ALEATORIA_GERADA
FLASK_DEBUG=0
```

`root` é o exemplo do repositório; configure o usuário disponível no seu ambiente. Não substitua um `.env` já configurado ao repetir a instalação. A chave de sessão deve ser própria: a aplicação rejeita uma chave vazia, mas não rejeita automaticamente o texto de exemplo.

```powershell
.\.venv\Scripts\python.exe app.py
```

Abra **http://127.0.0.1:5000**. Não é necessário ativar o ambiente virtual, o que evita depender da execução de `Activate.ps1`. Não abra o HTML diretamente ou pelo Live Server.

Em Linux/macOS, use `python3 -m venv .venv`, `.venv/bin/python -m pip install -r requirements.txt`, `cp .env.example .env` e, após configurar o arquivo, `.venv/bin/python app.py`.

O servidor está fixado em `127.0.0.1:5000` no `app.py`. Um sensor físico em outra máquina não consegue acessá-lo nesse endereço. Não há configuração de implantação externa pronta. A variável opcional `COOKIE_SECURE=1` habilita cookie somente por HTTPS; deixe-a ausente ou em `0` no teste HTTP local.

## Fluxo de integração implementado

1. O navegador carrega `/`; o JavaScript chama a API na mesma origem.
2. Cadastro grava `Cliente` e `Credencial`, usando hash de senha do Werkzeug, e inicia sessão. Login valida o hash e cria uma sessão por cookie; não usa JWT.
3. A sessão identifica o cliente. Unidades, cômodos, aparelhos, sensores e fontes são acessados com verificação de propriedade.
4. A API executa SQL parametrizado pelo MySQL Connector, abre conexão por contexto da requisição, confirma as gravações com `commit` e fecha a conexão ao final. Erros do conector acionam tentativa de rollback e resposta 500.
5. Simulações gravam `Consumo_Aparelho`. Sensores enviam potência e duração para `/api/iot/leituras`, autenticados por `X-Sensor-Key`, e gravam `Leitura_Sensor`.
6. O resumo agrega consumo e geração, calcula custo/projeção e consulta alertas. A interface consulta o resumo a cada 30 segundos quando está visível e há usuário/unidade selecionados.

### Regras de cálculo

- Energia do intervalo: `potenciaW × minutos / 60000`, em kWh.
- Se existir qualquer leitura IoT no período mensal de um cômodo, **todas as simulações desse cômodo são desconsideradas no resumo**, inclusive de outros dias.
- Consumo bruto: soma dos cômodos; líquido: `max(0, bruto - geração renovável)`; custo estimado: líquido × tarifa.
- Projeção: consumo bruto × dias do mês ÷ dia atual. É extrapolação linear, sem modelo de aprendizado de máquina.
- Meta mensal: aviso em 80% e limite em 100%, calculados sobre o consumo bruto. Alertas de cada tipo são gravados no máximo uma vez por unidade/mês pela lógica da aplicação.
- Pico IoT: potência >= 5.000 W gera `PICO_POTENCIA`, no máximo uma vez por unidade/dia pela lógica da aplicação.
- A checagem da meta ocorre ao simular, receber leitura ou salvar meta. Não existe agendador independente.
- Datas são atribuídas pelo servidor/banco. Os filtros do resumo usam início do mês como limite inferior, sem limite superior explícito; não há parâmetro de período nem configuração explícita de fuso.
- O resumo traz os 12 alertas mais recentes da unidade, inclusive de meses anteriores.

## Tabelas e vínculos

| Tabela | Chave e relacionamento principal | Uso atual |
|---|---|---|
| Estado | PK ID_Estado | Consulta de UFs para endereços |
| Cliente | PK ID_Cliente; CPF e Email únicos | Cadastro e identificação do responsável |
| Endereco | PK ID_Endereco; FK Estado e Cliente | Endereço da unidade |
| Unidade_Consumidora | PK ID_Unidade; FK Cliente e Endereco | Agrupa os recursos do cliente |
| Fornecedor | PK ID_Fornecedor; FK Endereco | Apenas esquema; sem endpoint |
| Medidor | PK ID_Medidor; FK Unidade_Consumidora e Fornecedor | Apenas esquema; sem endpoint |
| Leituras_Tempo_Real | PK ID_Leitura; FK Medidor | Não utilizada pelo fluxo IoT atual |
| Meta_Consumo | PK ID_Meta; FK Unidade_Consumidora | Limite/aviso do mês, em MM/YYYY |
| Previsao_Consumo | PK ID_Previsao; FK Unidade_Consumidora | Projeção salva; coluna original chama-se **Cosumo_kWh** |
| Alerta | PK ID_Alerta; FK Unidade_Consumidora | Avisos de meta e pico |
| Credencial | PK/FK ID_Cliente | Senha_Hash |
| Configuracao_Unidade | PK/FK ID_Unidade | Nome, tipo e tarifa |
| Comodo | PK ID_Comodo; FK Unidade_Consumidora | Organização de aparelhos e sensores |
| Aparelho_Catalogo | PK ID_Tipo; Nome único | Tipos e potências de referência |
| Aparelho | PK ID_Aparelho; FK Comodo e Aparelho_Catalogo | Potência e nome personalizado |
| Consumo_Aparelho | PK ID_Consumo; FK Aparelho | Histórico de simulações |
| Sensor_IoT | PK ID_Sensor; FK Comodo | Nome e hash SHA-256 da chave |
| Leitura_Sensor | PK ID_Leitura; FK Sensor_IoT | Potência, duração, energia e data |
| Fonte_Renovavel | PK ID_Fonte; FK Unidade_Consumidora | Fonte SOLAR, EOLICA ou OUTRA |
| Geracao_Renovavel | PK ID_Geracao; FK Fonte_Renovavel | Energia gerada e data |

Há índices compostos por entidade/data nos históricos de consumo, sensores e geração. Não há views, particionamento ou banco especializado em séries temporais nos scripts.

Excluir um aparelho remove suas simulações por cascata. Excluir um cômodo remove aparelhos, sensores e seus históricos por cascata. Alertas já gravados não são recalculados por essas exclusões.

## Endpoints

Base local: `http://127.0.0.1:5000`. Envie objetos JSON com `Content-Type: application/json` nos POSTs que recebem campos. “Sessão” significa reutilizar o cookie obtido no cadastro/login. IDs na URL devem ser substituídos pelos retornados pela API.

| Método | Caminho | Autenticação | Corpo / resultado principal |
|---|---|---|---|
| GET | / | Pública | Interface HTML |
| POST | /api/auth/cadastro | Pública | nome, email, cpf, telefone, senha → id, nome (201); inicia sessão |
| POST | /api/auth/login | Pública | email, senha → id, nome (200) |
| POST | /api/auth/sair | Pública | Sem corpo obrigatório → mensagem (200); encerra sessão |
| GET | /api/auth/eu | Sessão | id, nome, email |
| GET | /api/estados | Pública | Lista: id, nome, sigla |
| GET / POST | /api/unidades | Sessão | GET lista id/nome/tipo/tarifa; POST nome, tipo, cep, rua, numero, estadoId; complemento e tarifa opcionais → id, nome (201) |
| GET / POST | /api/unidades/{id}/comodos | Sessão | GET lista id/nome; POST nome → id, nome (201) |
| DELETE | /api/comodos/{id} | Sessão | Remove cômodo e histórico → mensagem (200) |
| GET | /api/catalogo | Sessão | Lista: id, nome, potencia |
| GET / POST | /api/comodos/{id}/aparelhos | Sessão | GET lista id/tipo/nome/potencia; POST tipoId; nome e potencia opcionais → id (201) |
| DELETE | /api/aparelhos/{id} | Sessão | Remove aparelho e histórico → mensagem (200) |
| POST | /api/aparelhos/{id}/simular | Sessão | minutos → energiaKwh, observacao (201) |
| GET | /api/unidades/{id}/resumo | Sessão | Totais, custo, projeção, meta, cômodos, série diária e alertas |
| POST | /api/unidades/{id}/meta | Sessão | limite → limite, aviso (200); cria/atualiza meta do mês |
| POST | /api/unidades/{id}/previsoes | Sessão | Sem campos obrigatórios → previsaoMesKwh, dataPrevisao (200); cria/atualiza projeção para último dia do mês |
| GET / POST | /api/unidades/{id}/sensores | Sessão | GET lista id/nome/comodoId/comodo; POST nome, comodoId → id, chave, aviso (201) |
| POST | /api/iot/leituras | X-Sensor-Key | sensorId, potenciaW, duracaoMinutos → energiaKwh, modo (201) |
| GET / POST | /api/unidades/{id}/renovaveis | Sessão | GET lista id/nome/tipo; POST nome, tipo → id (201) |
| POST | /api/renovaveis/{id}/geracao | Sessão | energiaKwh → energiaKwh (201) |

GETs bem-sucedidos retornam 200. Não existem rotas PUT/PATCH nem CRUD completo para todas as entidades.

### Validação e respostas

- Cadastro: nome/e-mail até 100 caracteres; CPF com 11 dígitos após limpeza, **sem validação de dígitos verificadores**; telefone com 10–13 dígitos; senha com pelo menos 8 caracteres.
- Unidade: tipo `RESIDENCIA` ou `COMERCIO`; tarifa de 0 a 10, padrão 0,9; `numero` deve ser texto. Estado deve existir.
- Aparelho: potência inteira de 1 a 30.000 W; se omitida, usa o catálogo.
- Simulação: duração inteira de 1 a 43.200 minutos.
- Leitura IoT: potência de 0 a 30.000 W e duração inteira de 1 a 1.440 minutos.
- Meta: limite de 0,01 a 100.000 kWh.
- Geração: energia de 0,000001 a 1.000.000 kWh.
- Erros tratados usam `{"erro":"mensagem"}`: 400 (validação), 401 (sessão/credencial/chave inválida), 403 (cômodo de outra unidade no cadastro de sensor), 404 (recurso não encontrado ou não pertencente ao cliente), 409 (CPF/e-mail duplicado), 500 (erro MySQL).
- Erros padrão do Flask, como rota inexistente, método inválido ou corpo maior que 64 KiB, não têm conversão personalizada para esse formato JSON.
- Valores DECIMAL retornados diretamente do banco em algumas listagens podem aparecer como strings JSON; o resumo e os resultados de cálculos convertem valores para números explicitamente.

## Testar os endpoints com PowerShell

Com MySQL preparado e Flask rodando, abra outro terminal. Use somente dados fictícios em um banco de teste. O roteiro grava dados e deve ser executado com e-mail/CPF ainda não cadastrados.

### 1. Cadastro, sessão e consultas iniciais

```powershell
$base = "http://127.0.0.1:5000"
$cadastro = @{
    nome="Teste README"; email="teste.readme@example.com"
    cpf="12345678901"; telefone="11999999999"; senha="TesteLocal123!"
} | ConvertTo-Json
$usuario = Invoke-RestMethod -Method Post -Uri "$base/api/auth/cadastro" -ContentType "application/json" -Body $cadastro -SessionVariable sessao
Invoke-RestMethod -Uri "$base/api/auth/eu" -WebSession $sessao
$estados = Invoke-RestMethod -Uri "$base/api/estados"
$catalogo = Invoke-RestMethod -Uri "$base/api/catalogo" -WebSession $sessao
```

Para reutilizar uma conta existente, substitua o cadastro por:

```powershell
$login = @{email="teste.readme@example.com"; senha="TesteLocal123!"} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$base/api/auth/login" -ContentType "application/json" -Body $login -SessionVariable sessao
```

### 2. Unidade, cômodo, aparelho e simulação

Use os IDs retornados, sem presumir que começam em 1:

```powershell
$estado = $estados | Where-Object { $_.sigla -eq "SP" } | Select-Object -First 1
$tipo = $catalogo | Select-Object -First 1
$body = @{
    nome="Casa de teste"; tipo="RESIDENCIA"; cep="01000-000"
    rua="Rua de teste"; numero="100"; complemento=""
    estadoId=$estado.id; tarifa=0.9
} | ConvertTo-Json
$unidade = Invoke-RestMethod -Method Post -Uri "$base/api/unidades" -WebSession $sessao -ContentType "application/json" -Body $body
$comodo = Invoke-RestMethod -Method Post -Uri "$base/api/unidades/$($unidade.id)/comodos" -WebSession $sessao -ContentType "application/json" -Body '{"nome":"Sala"}'
$body = @{tipoId=$tipo.id; nome="Carga de teste"; potencia=1000} | ConvertTo-Json
$aparelho = Invoke-RestMethod -Method Post -Uri "$base/api/comodos/$($comodo.id)/aparelhos" -WebSession $sessao -ContentType "application/json" -Body $body
Invoke-RestMethod -Method Post -Uri "$base/api/unidades/$($unidade.id)/meta" -WebSession $sessao -ContentType "application/json" -Body '{"limite":1}'
Invoke-RestMethod -Method Post -Uri "$base/api/aparelhos/$($aparelho.id)/simular" -WebSession $sessao -ContentType "application/json" -Body '{"minutos":60}'
Invoke-RestMethod -Uri "$base/api/unidades/$($unidade.id)/resumo" -WebSession $sessao
```

Em uma unidade nova, espera-se `energiaKwh=1`, `totalKwh=1`, `custoEstimado=0.9` e alertas `META_AVISO` e `META_EXCEDIDA`.

### 3. Fonte renovável e previsão

```powershell
$fonte = Invoke-RestMethod -Method Post -Uri "$base/api/unidades/$($unidade.id)/renovaveis" -WebSession $sessao -ContentType "application/json" -Body '{"nome":"Painel de teste","tipo":"SOLAR"}'
Invoke-RestMethod -Method Post -Uri "$base/api/renovaveis/$($fonte.id)/geracao" -WebSession $sessao -ContentType "application/json" -Body '{"energiaKwh":0.2}'
Invoke-RestMethod -Uri "$base/api/unidades/$($unidade.id)/resumo" -WebSession $sessao
Invoke-RestMethod -Method Post -Uri "$base/api/unidades/$($unidade.id)/previsoes" -WebSession $sessao -ContentType "application/json" -Body '{}'
```

Antes de enviar IoT, espera-se `renovavelKwh=0.2`, `liquidoKwh=0.8` e `custoEstimado=0.72`. A projeção depende do dia em que o teste é executado.

### 4. Sensor e leitura autenticada

```powershell
$body = @{nome="Sensor de teste"; comodoId=$comodo.id} | ConvertTo-Json
$sensor = Invoke-RestMethod -Method Post -Uri "$base/api/unidades/$($unidade.id)/sensores" -WebSession $sessao -ContentType "application/json" -Body $body
$headers = @{"X-Sensor-Key"=$sensor.chave}
$body = @{sensorId=$sensor.id; potenciaW=1500; duracaoMinutos=2} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$base/api/iot/leituras" -Headers $headers -ContentType "application/json" -Body $body
Invoke-RestMethod -Uri "$base/api/unidades/$($unidade.id)/resumo" -WebSession $sessao
```

A chave é retornada somente na criação; o banco guarda seu hash. A leitura dispensa cookie de sessão e deve retornar `energiaKwh=0.05` e `modo="MEDICAO_IOT_RECEBIDA"`. Agora o cômodo usa origem `IOT`: o total passa de 1 para 0,05 kWh, pois a simulação é substituída. Com a geração de 0,2 kWh já registrada, o líquido fica zero. Alertas anteriores permanecem.

Este POST de teste não comprova medição física: ele apenas exercita a interface de ingestão. Não reenvie a mesma leitura como tentativa automática: não há deduplicação.

### 5. Casos de erro e encerramento

| Teste manual | Esperado |
|---|---|
| GET /api/auth/eu sem reutilizar cookie | 401 |
| Repetir cadastro com mesmo CPF/e-mail | 409 |
| Simular com `{"minutos":0}` | 400 |
| Enviar leitura com X-Sensor-Key incorreto | 401 |
| Acessar unidade inexistente ou de outro cliente | 404 |
| Enviar leitura de 5.000 W por 1 minuto com chave válida | 201 e alerta PICO_POTENCIA, se ainda não gerado naquele dia |

O PowerShell pode lançar exceção nos códigos HTTP de erro; confira o status e o corpo da resposta. Para sair:

```powershell
Invoke-RestMethod -Method Post -Uri "$base/api/auth/sair" -WebSession $sessao
```

Para conferir os DELETEs, use apenas recursos descartáveis: `DELETE /api/aparelhos/{id}` e `DELETE /api/comodos/{id}`, autenticados. Ambos removem históricos associados, sem recuperação implementada.

## Limitações e informações ausentes

- **Não disponíveis no repositório:** testes automatizados, especificação OpenAPI/Swagger, coleção Postman, configuração Docker, pipeline de CI, migrações e configuração de implantação em produção.
- **Integração física não demonstrada:** não há firmware, modelo de hardware validado ou rotina de envio. A API recebe intervalos de potência/duração; não recebe leituras acumuladas do medidor.
- **Escopo de dados:** Fornecedor, Medidor e Leituras_Tempo_Real permanecem apenas no modelo SQL. O resumo não consulta essas tabelas.
- **Sem notificações externas:** alertas são registros no banco exibidos no painel; não há envio por e-mail/push.
- **Sem histórico consultável por período via endpoint dedicado:** o resumo trabalha com o mês corrente. Não há parâmetros de paginação ou exportação.
- **Estimativas:** tarifa é manual, custo não representa fatura com impostos/bandeiras, e previsão não modela padrões horários/semanais.
- **Protótipo local:** há hash de senhas, cookie HttpOnly/SameSite e verificação de proprietário, mas não há proteção CSRF dedicada, limitação de tentativas de login ou configuração WSGI/HTTPS pronta.
- **Consistência temporal:** não há tratamento explícito de diferenças de fuso entre Python e MySQL; alinhe os ambientes para evitar divergências de dia/mês.
- **Cópias TXT:** `documentos_txt/app.py.txt` e `documentos_txt/sql__02_complementos.sql.txt` diferem dos arquivos ativos. Para execução e manutenção, use `app.py` e `sql/`.

## Problemas comuns

| Sintoma | Verificação |
|---|---|
| Configure SECRET_KEY no arquivo .env | Preencha SECRET_KEY e execute a partir da pasta do projeto |
| Access denied for user | Confira usuário, senha e permissões MySQL |
| Can't connect to MySQL server | Confira serviço, DB_HOST e DB_PORT |
| Unknown database / Table doesn't exist | Confira o esquema e a aplicação dos dois scripts, respeitando banco existente |
| Table Credencial already exists | O complemento não é integralmente idempotente; revise antes de reaplicar |
| No module named flask/mysql/dotenv | Instale requirements.txt com o mesmo Python usado para iniciar |
| Porta 5000 ocupada | Encerre a instância anterior ou ajuste a porta em app.py |
| 401 após login no navegador ao testar no terminal | Navegador e PowerShell têm sessões distintas; autentique o terminal e reutilize -WebSession |
