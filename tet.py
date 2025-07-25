import json
import psycopg2

# Connexion PostgreSQL
conn = psycopg2.connect(
    dbname="storemngm",
    user="postgres",
    password="ton_mot_de_passe",
    host="localhost",
    port="5432"
)
cur = conn.cursor()

# Charger le fichier JSON
with open("data/users.json", encoding="utf-8") as f:
    users = json.load(f)

# Insérer dans la base
for user in users:
    cur.execute("""
        INSERT INTO users (username, password, role, salary, activated)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        user['username'],
        user['password'],
        user['role'],
        user['salary'],
        bool(user['activated'])
    ))

conn.commit()
cur.close()
conn.close()
