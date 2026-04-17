#!/usr/bin/env python
from pathlib import Path
from biblioforge.services.sheets_sync_service import SheetsSyncService
from biblioforge.repositories.book_repository import BookRepository

# Create a test instance  
state_path = Path('biblioforge/data/processed/sheets_sync_state.json')
repo = BookRepository(Path('biblioforge/data/processed/books.json'))

service = SheetsSyncService(repo, repo, state_path)

print('Service account file:', service.service_account_file)
print('Resolved path:', service._resolve_service_account_path(service.service_account_file))
print('Resolved path exists:', service._resolve_service_account_path(service.service_account_file).exists())
print('State path parent:', service.state_path.parent)

# Test candidates
print('\nTesting candidates:')
candidates = [
    Path.cwd() / service.service_account_file,
    service.state_path.parent / service.service_account_file,
    service.package_root / service.service_account_file,
    service.project_root / service.service_account_file,
]
for candidate in candidates:
    print(f"  {candidate} -> exists: {candidate.exists()}")

