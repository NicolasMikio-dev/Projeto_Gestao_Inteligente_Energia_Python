"""Aplica os dois scripts originais ao banco selecionado pelo Railway."""
import os
import re
import time
from pathlib import Path

import mysql.connector

from app import app, get_connection


SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
SCRIPTS = ("01_banco_original.sql", "02_complementos.sql")


def sql_para_deploy(arquivo):
    # A conexão já selecionou DB_NAME. Os arquivos locais continuam intactos.
    linhas = arquivo.read_text(encoding="utf-8-sig").splitlines()
    comandos_locais = {
        "CREATE DATABASE gestao_inteligente_de_energia;",
        "USE gestao_inteligente_de_energia;",
    }
    # O segundo arquivo também contém comentários que começam com "--CREATE".
    texto = "\n".join(
        linha for linha in linhas
        if linha.strip() not in comandos_locais and not linha.lstrip().startswith("--")
    )
    # O DDL do MySQL pode persistir mesmo após uma falha no meio do arquivo.
    return re.sub(
        r"(?im)^CREATE TABLE (?!IF NOT EXISTS\b)", "CREATE TABLE IF NOT EXISTS ", texto
    )


def aguardar_mysql():
    for tentativa in range(1, 11):
        try:
            return get_connection()
        except mysql.connector.Error as erro:
            if erro.errno not in (2002, 2003, 2005, 2013, 2055) or tentativa == 10:
                raise
            print(f"Aguardando o serviço MySQL ({tentativa}/10)...")
            time.sleep(3)


def inicializar():
    obrigatorias = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
    ausentes = [nome for nome in obrigatorias if not os.getenv(nome)]
    if ausentes:
        raise RuntimeError("Defina estas variáveis na API: " + ", ".join(ausentes))

    with app.app_context():
        db = aguardar_mysql()
        with db.cursor(buffered=True) as cursor:
            # A conexão libera o lock ao sair do contexto, inclusive após falha.
            cursor.execute("SELECT GET_LOCK('energia_mais_inicializacao', 60)")
            if cursor.fetchone()[0] != 1:
                raise RuntimeError("Outra publicação está preparando o MySQL. Repita o deploy.")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Energia_Deploy (
                    Arquivo VARCHAR(128) PRIMARY KEY,
                    Aplicado_Em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            for nome in SCRIPTS:
                cursor.execute("SELECT 1 FROM Energia_Deploy WHERE Arquivo = %s", (nome,))
                if cursor.fetchone():
                    print(f"Já aplicado: {nome}")
                    continue
                print(f"Aplicando {nome}...")
                cursor.execute(sql_para_deploy(SQL_DIR / nome))
                while cursor.nextset():
                    pass
                cursor.execute("INSERT INTO Energia_Deploy (Arquivo) VALUES (%s)", (nome,))
                db.commit()
            print("Banco preparado.")


if __name__ == "__main__":
    inicializar()
