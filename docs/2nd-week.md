# Вторая неделя: инфраструктура

## Результат этапа

Подготовлено базовое окружение для локальной разработки. Запуск инфраструктуры выполняется через Docker Compose. Добавлена единая точка входа API Gateway.

Проверено в Docker:

- все основные контейнеры находятся в состоянии `healthy`;
- Gateway отвечает на `/api/v1/health`;
- LocalStack сообщает, что сервис S3 доступен;
- PostgreSQL содержит все семь изолированных баз сервисов;
- конфигурация проходит `docker compose config --quiet`.

## Состав Docker Compose

- PostgreSQL 16 — реляционные данные.
- RabbitMQ 3 с management-интерфейсом — доменные события.
- Redis 7 — кеширование, временное состояние и ограничение частоты запросов.
- LocalStack с сервисом S3 — совместимое с S3 хранилище изображений.
- API Gateway на FastAPI — публичная точка входа.

PostgreSQL при первом запуске создаёт изолированные логические базы:

- `auth_db`.
- `catalog_db`.
- `deals_db`.
- `payment_db`.
- `delivery_db`.
- `chat_db`.
- `reviews_db`.

Микросервисы не будут обращаться к чужим базам и будут использовать только собственные базы или схемы.

## Структура Gateway

```text
backend/gateway/
├── app/
│   ├── __init__.py
│   └── main.py
├── Dockerfile
└── requirements.txt
```

Gateway предоставляет базовые health-эндпоинты:

- `GET /api/v1/health`.
- `GET /api/v1`.

В данном этапе Gateway не содержит маршруты бизнес-сервисов: они будут добавляться по мере создания сервисов.

## Переменные окружения

Файл `.env.example` содержит необходимые настройки PostgreSQL, RabbitMQ, Redis, LocalStack и JWT. Реальные секреты не добавляются в репозиторий.

Перед запуском можно создать рабочий файл окружения:

```powershell
Copy-Item .env.example .env
```

## Запуск

```powershell
docker compose up --build -d
docker compose ps
```

Проверить Gateway:

```powershell
curl http://localhost:8000/api/v1/health
```

Проверить веб-интерфейсы инфраструктуры:

- RabbitMQ: `http://localhost:15672`.
- S3 endpoint: `http://localhost:4566`.

## Проверка остановки и перезапуска

```powershell
docker compose down
docker compose up -d
docker compose ps
```

Данные PostgreSQL, RabbitMQ, Redis и LocalStack сохраняются в Docker volumes.

## Частичный результат этапа 3: сервис авторизации

Реализован независимый сервис `auth-service`:

- отдельный Dockerfile и Alembic-миграции;
- база `auth_db`;
- модели ролей, пользователей и refresh-токенов;
- регистрация и вход;
- хеширование паролей Argon2;
- access-токены JWT и ротация refresh-токенов;
- получение и изменение собственного профиля;
- выход и отзыв refresh-токена;

Сервис доступен внутри Compose на порту `8001`, а публичные routes Gateway доступны через `/api/v1`.

Проверенные HTTP-сценарии:

- регистрация пользователя;
- вход по email и паролю;
- получение профиля с access-токеном;
- обновление профиля;
- ротация refresh-токена;
- повторное использование старого refresh-токена отклоняется;
- выход отзывает refresh-токен;
- маршрутизация через Gateway на порту `8000`.

## Сервис каталога

Добавлен независимый `catalog-service` с базой `catalog_db`:

- категории, темы и объявления;
- описание состояния и комплектности LEGO;
- цена хранится в `NUMERIC`, не во float;
- поиск по названию, фильтры по категории, теме, состоянию и цене;
- сортировка по дате и цене, пагинация;
- избранное с защитой от повторного добавления;
- редактирование и архивирование только своего объявления;
- проверка допустимого статуса перед изменением;
- загрузка до 10 изображений на объявление;
- проверка формата JPEG/PNG/WebP, размера до 5 МБ и разрешения;
- хранение изображений в S3 через LocalStack;
- просмотр и удаление изображения через Gateway.

При первой миграции создаются три категории и темы City, Star Wars, Technic, NINJAGO, Creator, Friends и Architecture.

Основные публичные маршруты:

- `GET /api/v1/catalog/categories`.
- `GET /api/v1/catalog/themes`.
- `GET /api/v1/catalog/listings`.
- `GET /api/v1/catalog/favorites`.
- `POST /api/v1/catalog/listings`.
- `GET`, `PATCH`, `DELETE /api/v1/catalog/listings/{id}`.
- `POST /api/v1/catalog/listings/{id}/images`.
- `GET /api/v1/catalog/images/{key}`.
- `DELETE /api/v1/catalog/listings/{id}/images/{image_id}`.
- `POST`, `DELETE /api/v1/catalog/listings/{id}/favorites`.

Интеграционный тест проверяет создание объявления и фото, поиск, избранное, ограничения доступа и архивирование.