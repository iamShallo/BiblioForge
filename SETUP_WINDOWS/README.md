# BiblioForge - Setup Windows

## Requisiti
- Windows 10 o superiore
- Python 3.8+ installato sul sistema

> **IMPORTANTE:** Durante l'installazione di Python, **DEVI selezionare il checkbox "Add Python to PATH"**

## Installazione Automatica

1. **Estrai il file ZIP** nella cartella desiderata
2. **Naviga nella cartella `SETUP_WINDOWS`**
3. **Fai doppio click sul file `setup_and_run.bat`**

Lo script automaticamente:
- ✅ Cerca Python nel sistema
- ✅ Crea un ambiente virtuale Python
- ✅ Installa tutte le dipendenze dal file requirements.txt
- ✅ Avvia il programma BiblioForge

## Errore "Python non trovato"

Se il .bat mostra l'errore **"[ERROR] Python non trovato nel sistema"**:

### Soluzione 1: Installare Python correttamente
1. Scarica Python da: https://www.python.org/downloads/
2. Avvia l'installer
3. **IMPORTANTE**: Spunta il checkbox "**Add Python to PATH**" in basso a sinistra dell'installer
4. Seleziona "Install Now" oppure personalizza l'installazione
5. Attendi il completamento
6. **Riavvia il computer** (consigliato)
7. Riapri il file `setup_and_run.bat`

### Soluzione 2: Aggiungere Python al PATH manualmente
Se hai Python installato ma il PATH non è stato configurato:

1. Apri **Pannello di Controllo**
2. Vai a **Sistema e sicurezza** → **Sistema**
3. Clicca su **Impostazioni di sistema avanzate** (a sinistra)
4. Clicca sul pulsante **Variabili di ambiente** in basso
5. Sotto "Variabili di sistema", trova **Path** e clicca **Modifica**
6. Clicca **Nuovo** e aggiungi il percorso di Python:
   - Solitamente: `C:\Users\TuoNome\AppData\Local\Programs\Python\Python3XX`
   - oppure: `C:\Program Files\Python3XX`
   - (sostituisci `XX` con la versione, es: Python311)
7. Clicca **OK** su tutte le finestre
8. **Riavvia il computer**
9. Riapri il file `setup_and_run.bat`

## Cosa farà il programma

Al primo avvio, il programma avvierà una **dashboard Streamlit** nel tuo browser predefinito su `http://localhost:8501`

Se il browser non si apre automaticamente, copia e incolla manualmente l'URL nella barra degli indirizzi.

## Uscire dal programma

Nel CMD dove è in esecuzione il programma, premi `Ctrl+C`

## Riavviare il programma

Nei successivi utilizzi, puoi:
- Rifare doppio click su `setup_and_run.bat` oppure
- Aprire PowerShell/CMD nella cartella radice del progetto e eseguire:
  ```powershell
  .venv\Scripts\Activate.ps1
  python main.py dashboard
  ```

## Troubleshooting

### Il programma non si avvia ancora
- Verifica che Python sia nel PATH: apri CMD e digita `python --version`
- Se mostra la versione, il PATH è corretto

### Errore durante l'installazione dei requirements
- Prova a eseguire il .bat di nuovo
- A volte è un problema temporaneo di connessione

### La porta 8501 è già in uso
- Un'altra istanza di Streamlit è in esecuzione
- Chiudi tutti i terminali con BiblioForge e prova di nuovo

## Supporto

Per problemi o domande, contatta: francesco.caldarelli@studenti.unicam.it

## Cosa farà il programma

Al primo avvio, il programma avvierà una **dashboard Streamlit** nel tuo browser predefinito su `http://localhost:8501`

Se il browser non si apre automaticamente, copia e incolla manualmente l'URL nella barra degli indirizzi.

## Uscire dal programma

Nel terminale dove è in esecuzione il programma, premi `Ctrl+C`

## Riavviare il programma

Nei successivi utilizzi, puoi:
- Rifare doppio click su `setup_and_run.bat` oppure
- Aprire un terminale nella cartella radice del progetto e eseguire:
  ```
  .venv\Scripts\activate.bat
  python main.py dashboard
  ```

## Troubleshooting

### Il programma non si avvia
- Verifica che Python sia installato: apri cmd e digita `python --version`
- Prova ad eseguire `setup_and_run.bat` da un terminale per vedere l'errore esatto

### Errore "Python non trovato"
- Reinstalla Python da https://www.python.org/ assicurandoti di selezionare "Add Python to PATH" durante l'installazione

### La porta 8501 è già in uso
- Un'altra istanza di Streamlit è in esecuzione
- Chiudi tutti i terminali con BiblioForge in esecuzione e prova di nuovo

## Supporto

Per problemi o domande, contatta: francesco.caldarelli@studenti.unicam.it
