CREATE DATABASE gestao_inteligente_de_energia;
USE gestao_inteligente_de_energia;



-- Tabelas independentes não recebem FK-------------------------------------------------------------------

CREATE TABLE Estado (
	ID_Estado INT AUTO_INCREMENT PRIMARY KEY,
	Nome Varchar(100) NOT NULL,
	Sigla CHAR(2) NOT NULL,
	Pais VARCHAR(100) NOT NULL
);

CREATE TABLE Cliente(
	ID_Cliente INT AUTO_INCREMENT PRIMARY KEY,
	Nome_Cliente VARCHAR(100) NOT NULL,
	CPF VARCHAR(11) UNIQUE NOT NULL,
	Email VARCHAR(100) UNIQUE NOT NULL,
	Telefone VARCHAR(13) NOT NULL
);



-- Tabela endereço---------------------------------------------------------------------------------------

CREATE TABLE Endereco (
	ID_Endereco INT AUTO_INCREMENT PRIMARY KEY,
	Cep VARCHAR(9) NOT NULL,
	Rua VARCHAR(100) NOT NULL,
	Numero VARCHAR(10) NOT NULL,
	Complemento VARCHAR(100) NOT NULL,
	ID_Estado INT NOT NULL,
	ID_Cliente INT NOT NULL,
	FOREIGN KEY (ID_Estado) REFERENCES Estado(ID_Estado),
	FOREIGN KEY (ID_Cliente) REFERENCES Cliente(ID_Cliente)
);



-- tabelas que precisam da TABELA ENDEREÇO ------------------------------------------------------------------

CREATE TABLE Fornecedor (
	ID_Fornecedor INT AUTO_INCREMENT PRIMARY KEY,
	Nome_Fornecedor VARCHAR (100) NOT NULL,
	CNPJ VARCHAR (14) UNIQUE NOT NULL, 
	Matriz_Energica VARCHAR (50) NOT NULL,
	Email VARCHAR(100) NOT NULL,
	Telefone VARCHAR(13) NOT NULL,
	ID_Endereco INT NOT NULL,
	FOREIGN KEY (ID_Endereco) REFERENCES Endereco(ID_Endereco)
);

CREATE TABLE Unidade_Consumidora (
	ID_Unidade INT AUTO_INCREMENT PRIMARY KEY,
	ID_Cliente INT NOT NULL,
	ID_Endereco INT NOT NULL,
	FOREIGN KEY (ID_Cliente) REFERENCES Cliente(ID_Cliente),
	FOREIGN KEY (ID_Endereco) REFERENCES Endereco(ID_Endereco)
);



-- Tabela ponte entre Unidade Consumidora e Fornecedor------------------------------------------------------

CREATE TABLE Medidor (
	ID_Medidor INT AUTO_INCREMENT PRIMARY KEY,
	Modelo VARCHAR(50) NOT NULL,
	Data_Instalação DATE NOT NULL,
	ID_Unidade INT NOT NULL,
	ID_Fornecedor INT NOT NULL,
	FOREIGN KEY (ID_Unidade) REFERENCES Unidade_Consumidora (ID_Unidade),
	FOREIGN KEY (ID_Fornecedor) REFERENCES Fornecedor(ID_Fornecedor)
);



-- Tabelas Operacionais e de Calculos que dependem da Unidade_Consumidora------------------------------------

CREATE TABLE Meta_Consumo (
	ID_Meta INT AUTO_INCREMENT PRIMARY KEY,
	Mes_Ano VARCHAR(7) NOT NULL,           /* Formato MM/YYYY */
	Limite_kWh DECIMAL (10,2) NOT NULL,
	Valor_Alerta_kWh DECIMAL (10,2) NOT NULL,
	ID_Unidade INT NOT NULL,
	FOREIGN KEY (ID_Unidade) REFERENCES Unidade_Consumidora (ID_Unidade)
);


CREATE TABLE Previsao_Consumo(
	ID_Previsao INT AUTO_INCREMENT PRIMARY KEY,
	Cosumo_kWh DECIMAL (10,2) NOT NULL,
	Data_Previsao DATE NOT NULL,
	Possibilidade VARCHAR(50) NOT NULL,
	ID_Unidade INT NOT NULL,
	FOREIGN KEY (ID_Unidade) REFERENCES Unidade_Consumidora(ID_Unidade)
);


CREATE TABLE Alerta(
	ID_Alerta INT AUTO_INCREMENT PRIMARY KEY,
	Tipo_Alerta VARCHAR(100) NOT NULL,
	Mensagem TEXT NOT NULL,
	Data_Hora DATETIME NOT NULL,
	ID_Unidade INT NOT NULL,
	FOREIGN KEY (ID_Unidade) REFERENCES Unidade_Consumidora(ID_Unidade)
);


CREATE TABLE Leituras_Tempo_Real(
ID_Leitura INT AUTO_INCREMENT PRIMARY KEY,
Data_Hora DATETIME NOT NULL,
Consumo_kWh DECIMAL(10,2) NOT NULL,
ID_Medidor INT NOT NULL,
FOREIGN KEY (ID_Medidor) REFERENCES Medidor(ID_Medidor)
);