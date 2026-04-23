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

### Lo script ha gia' cercato in:
- Variabile PATH di sistema
- Python Launcher di Windows (`py`)
- `C:\Program Files\Python*`
- `C:\Program Files (x86)\Python*`
- `AppData\Local\Programs\Python\Python*`
- `AppData\Local\Programs\Python*`
- Registro di Windows

### Soluzione 1: Installa Python correttamente (CONSIGLIATO)
1. Scarica Python da: https://www.python.org/downloads/
2. Avvia l'installer
3. **MOLTO IMPORTANTE**: Spunta il checkbox **"Add Python to PATH"** (in basso a sinistra)
4. Scegli **"Install for all users"** (se hai permessi admin)
5. Completa l'installazione
6. **Riavvia il computer** (importante!)
7. Riapri il file `setup_and_run.bat`

### Soluzione 2: Aggiungi Python al PATH manualmente
Se Python è gia' installato ma il PATH non è stato configurato:

1. Apri **Esplora File** (Windows Explorer)
2. Clicca su **"Questo PC"** nel menu a sinistra
3. Nella barra degli indirizzi, scrivi: `%APPDATA%\..\Local\Programs`
4. Premi Invio
5. Cerca una cartella che inizia con **Python** (es: `Python314`)
6. Apri quella cartella e verifica che dentro ci sia **python.exe**
7. Copia il percorso completo dalla barra degli indirizzi (es: `C:\Users\claud\AppData\Local\Programs\Python314`)
8. Ora aggiungi al PATH:
   - Premi il tasto Windows + R
   - Scrivi: `sysdm.cpl`
   - Premi Invio
   - Vai alla scheda **"Avanzate"**
   - Clicca **"Variabili di ambiente"** in basso
   - Sezione "Variabili di sistema", trova **Path** e clicca **"Modifica"**
   - Clicca **"Nuovo"**
   - Incolla il percorso copiato (es: `C:\Users\claud\AppData\Local\Programs\Python314`)
   - Clicca **OK** su tutte le finestre
   - **Riavvia il computer**
   - Riapri il file `setup_and_run.bat`

### Soluzione 3: Specifica il percorso manualmente nello script
Se hai trovato il percorso di Python ma vuoi usarlo subito:

1. Apri il file **`setup_and_run.bat`** con **Blocco Note** (tasto destro → Apri con → Blocco Note)
2. Vai alla riga 10 (subito dopo `cd ../BiblioForge`)
3. Aggiungi una nuova riga con:
   ```batch
   set "PYTHON_PATH=C:\Users\claud\AppData\Local\Programs\Python314\python.exe"
   ```
   _(sostituisci il percorso con quello dove hai Python)_
4. Salva il file (Ctrl+S)
5. Riapri il file `setup_and_run.bat`

### Come trovare il percorso esatto di Python
Se non sai dove è installato Python:

**Metodo 1: Usa il Prompt dei Comandi**
1. Apri **Prompt dei Comandi** (premi Windows, scrivi `cmd`, premi Invio)
2. Scrivi: `where python`
3. Premi Invio
4. Copiarai il percorso completo di python.exe

In alternativa, prova anche:
- `py --version`
- `py -c "import sys; print(sys.executable)"`

**Metodo 2: Controlla il registro di Windows**
1. Premi Windows + R
2. Scrivi: `regedit`
3. Premi Invio
4. Naviga a: `HKEY_CURRENT_USER\Software\Python\PythonCore`
5. Vedrai cartelle come `3.14`, `3.13`, ecc.
6. Apri una di loro e cerca la chiave `InstallPath`
7. Il valore mostrato sarà il percorso di Python

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
