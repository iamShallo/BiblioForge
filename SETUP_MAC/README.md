# BiblioForge - Setup macOS

## Requisiti
- macOS 10.14+
- Python 3.8+ installato sul sistema

## Avvio con doppio click

1. Estrai il file ZIP nella cartella desiderata
2. Apri la cartella estratta
3. Apri la cartella SETUP_MAC
4. Fai doppio click su setup_and_run.command

Il file .command apre automaticamente il Terminale e:
- crea un ambiente virtuale Python
- installa i requirements
- avvia la dashboard in locale

## Dove si apre il programma

La dashboard parte su:
- http://localhost:8501

## Uscita

Nel terminale aperto automaticamente, premi Ctrl+C per fermare il programma.

## Problemi comuni

### "python3 non trovato"
Installa Python da:
- https://www.python.org/
oppure con Homebrew:
- brew install python3

### "developer cannot be verified" al primo doppio click
macOS può bloccare i file scaricati. Se succede:
1. click destro su setup_and_run.command
2. Apri
3. Conferma l'apertura

## Supporto

francesco.caldarelli@studenti.unicam.it
