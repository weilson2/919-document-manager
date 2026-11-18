from alembic import context

from document_manager.persistence.models import Base

context.configure(
    connection=context.config.attributes["connection"],
    target_metadata=Base.metadata,
    render_as_batch=True,
    transactional_ddl=True,
)

with context.begin_transaction():
    context.run_migrations()
