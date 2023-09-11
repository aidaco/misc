-- name: ensure_table
CREATE TABLE IF NOT EXISTS User (id INTEGER PRIMARY KEY, name TEXT);

-- name: insert_user
INSERT INTO User (name) VALUES (:name);

-- name: update_user
UPDATE User SET (name) = (:name) WHERE id=:id;
