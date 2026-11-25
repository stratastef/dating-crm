import sqlalchemy as sa


def user_id_column() -> sa.Column:
    """The owner column every tenant table must have. Use it in `op.create_table(...)`."""
    return sa.Column(
        "user_id",
        sa.BigInteger,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
