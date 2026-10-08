## Run Alembic Migrations

## Configuration

```bash
cp alembic.ini.example alembic.i
```

- Update the `alembic.ini` with your database credentials (`sqlalchemy.url`)


### create new migrations
```bash
alembic revision --autogenerate -m "add ..... "
```


### upgrade the database 
```bash
alembic upgrade head
```