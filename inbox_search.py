SEARCHABLE_INBOX_FIELDS = ("from_name", "from_mail", "to_mail", "subject", "body")


def normalize_inbox_search_query(query):
    return str(query or "").strip().lower()


def filter_inbox_emails(emails_df, query):
    normalized_query = normalize_inbox_search_query(query)
    if not normalized_query:
        return emails_df

    searchable_fields = [
        field for field in SEARCHABLE_INBOX_FIELDS if field in emails_df.columns
    ]
    if not searchable_fields:
        return emails_df

    matches = None
    for field in searchable_fields:
        field_matches = (
            emails_df[field]
            .fillna("")
            .astype(str)
            .str.lower()
            .str.contains(normalized_query, regex=False, na=False)
        )
        matches = field_matches if matches is None else matches | field_matches

    return emails_df[matches].copy()
