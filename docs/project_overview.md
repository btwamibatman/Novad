# Project Overview

ProcessFlow API is a small backend project for workflow management. It uses demo data and focuses on clear backend structure.

## Architecture

The project uses a simple layered structure. Each layer has one main responsibility, which makes the code easier to read, test and extend.

## FastAPI App Layer

The FastAPI application starts in `app/main.py`. It creates the API object, registers routes and initializes database tables when the application starts.

The API routes are grouped by resource:

- workflow iterations
- tasks
- resources
- activity notes
- comments
- dashboard

The internal route paths keep the existing names: `weeks`, `tools` and `notes`.

## SQLAlchemy Models

SQLAlchemy models are stored in `app/models`. They describe database tables:

- `Week` for workflow iterations
- `Task`
- `Tool` for resources
- `Note` for activity notes
- `TaskComment`

The models define table columns, foreign keys and relationships. For example, a task belongs to one workflow iteration through `week_id`.

## Pydantic Schemas

Pydantic schemas are stored in `app/schemas`. They describe request and response data.

Schemas are used for input validation, response formatting and Swagger UI documentation. For example, task status can only be `planned`, `in_progress` or `completed`, and task priority can only be `low`, `medium` or `high`.

## CRUD Layer

The CRUD layer is stored in `app/crud`. It contains database operations such as listing, creating, updating and deleting records.

Routes call CRUD functions instead of writing database logic directly inside endpoint functions. This keeps routes focused on HTTP behavior.

## PostgreSQL Database

PostgreSQL is the main documented database. Docker Compose starts a PostgreSQL container and passes the connection string to the API through environment variables.

The application also has a simple SQLite fallback for local development without Docker.

## Docker Environment

Docker Compose starts two services:

- `db`: PostgreSQL database
- `api`: FastAPI backend application

The API is available at `http://localhost:8000`. Swagger UI is available at `http://localhost:8000/docs`.

## Why This Structure Is Useful

The project is small enough to understand, but it still demonstrates real backend concepts:

- REST API design
- database tables and relationships
- validation
- error handling
- Docker containerization
- automated tests
- simple static dashboard
