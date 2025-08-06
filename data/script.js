document.addEventListener('DOMContentLoaded', () => {

    // --- ZMIENNE GLOBALNE ---
    let currentProgram = [];
    let sortable;
    let programTimerInterval = null;
    let activeStepData = { index: -1, startTime: 0, totalDuration: 0 };
    let editingStepIndex = -1;

    // --- ELEMENTY UI ---
    const statusReagentValvePos = document.getElementById('status-reagent-valve-pos');
    const statusReagentValveState = document.getElementById('status-reagent-valve-state');
    const statusColumnValvePos = document.getElementById('status-column-valve-pos');
    const statusColumnValveState = document.getElementById('status-column-valve-state');
    const statusPumpFlowRate = document.getElementById('status-pump-flow-rate');
    const statusPumpVolume = document.getElementById('status-pump-volume');
    const statusPumpDirection = document.getElementById('status-pump-direction');
    const statusProgram = document.getElementById('status-program');
    const btnSetValves = document.getElementById('btn-set-valves');
    const pumpFlowRateInput = document.getElementById('pump-flow-rate-input');
    const pumpAccelInput = document.getElementById('pump-accel-input');
    pumpAccelInput.step = "0.1";
    const btnSetPump = document.getElementById('btn-set-pump');
    const btnStopPump = document.getElementById('btn-stop-pump');
    const btnReversePump = document.getElementById('btn-reverse-pump');
    const programCard = document.querySelector('.program-view').closest('.card');
    const progReagent = document.getElementById('prog-reagent');
    const progFlowRate = document.getElementById('prog-flow-rate');
    const progFlushDuration = document.getElementById('prog-flush-duration');
    const btnAddFlushStep = document.getElementById('btn-add-flush-step');
    const progWaitDuration = document.getElementById('prog-wait-duration');
    const btnAddWaitStep = document.getElementById('btn-add-wait-step');
    const programStepsList = document.getElementById('program-steps-list');
    const btnRunProgram = document.getElementById('btn-run-program');
    const btnStopProgram = document.getElementById('btn-stop-program');
    const btnClearProgram = document.getElementById('btn-clear-program');
    const btnSaveProgram = document.getElementById('btn-save-program');
    const btnLoadProgram = document.getElementById('btn-load-program');
    const loadProgramInput = document.getElementById('load-program-input');
    const dropZone = document.getElementById('drop-zone');
    const editModal = document.getElementById('edit-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalBody = document.getElementById('modal-body');
    const btnSaveChanges = document.getElementById('btn-save-changes');
    const btnCancelEdit = document.getElementById('btn-cancel-edit');
    const btnOpenConfig = document.getElementById('btn-open-config');
    const configModal = document.getElementById('config-modal');
    const btnSaveConfig = document.getElementById('btn-save-config');
    const btnCancelConfig = document.getElementById('btn-cancel-config');

    // --- WALIDACJA PÓL INPUT ---
    const inputsToValidate = [
        // Pola sterowania ręcznego
        pumpFlowRateInput,
        pumpAccelInput,
        // Pola edytora programu
        progFlowRate,
        progFlushDuration,
        progWaitDuration
    ];

    function validateInputOnBlur(event) {
        const inputElement = event.target;
        const min = parseFloat(inputElement.min);
        const max = parseFloat(inputElement.max);
        let value = parseFloat(inputElement.value);

        if (isNaN(value)) {
            // If input is not a number, reset to default or min value
            inputElement.value = inputElement.defaultValue || min;
            return;
        }

        if (value < min) {
            inputElement.value = min;
        } else if (value > max) {
            inputElement.value = max;
        }
    }

    inputsToValidate.forEach(input => {
        input.addEventListener('blur', validateInputOnBlur);
    });


    // --- FUNKCJE POMOCNICZE ---
    let reagentNames = {}; // Cache nazw reagentów

    function translateValveState(state) {
        switch (state) {
            case 0: return "Bezczynny";
            case 1: return "Bazowanie";
            case 2: return "Zatrzymany";
            case 3: return "W ruchu";
            default: return "Nieznany";
        }
    }
    function translateValvePosition(position) {
        if (position === 255) return "unknown";
        return position + 1;
    }
    function formatTime(ms) {
        if (ms < 0) ms = 0;
        const totalSeconds = Math.floor(ms / 1000);
        const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, '0');
        const seconds = (totalSeconds % 60).toString().padStart(2, '0');
        return `${minutes}:${seconds}`;
    }

    // --- LOGIKA ---

    /**
     * @brief Pobiera aktualny program z urządzenia i odświeża listę kroków w UI.
     */
    async function loadProgramFromServer() {
        try {
            const response = await fetch('/api/program/get');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const loadedProgram = await response.json();
            if (Array.isArray(loadedProgram) && loadedProgram.length > 0) {
                console.log("Program loaded from device on startup.");
                currentProgram = loadedProgram;
                renderProgramList();
            }
        } catch (error) {
            console.error("Could not load program from device on startup:", error);
        }
    }

    /**
     * @brief Pobiera konfigurację reagentów z urządzenia.
     */
    async function loadReagentConfigFromServer() {
        try {
            const response = await fetch('/api/reagent-config/get');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const config = await response.json();
            reagentNames = config;
            console.log("Reagent configuration loaded from device.");
            updateReagentSelectOptions();
        } catch (error) {
            console.error("Could not load reagent configuration from device:", error);
        }
    }

    /**
     * @brief Aktualizuje opcje w select elementach z nazwami reagentów.
     */
    function updateReagentSelectOptions() {
        const select = document.getElementById('prog-reagent');
        if (!select) return;

        // Wyczyść istniejące opcje
        select.innerHTML = '';

        // Dodaj nowe opcje z nazwami reagentów
        for (let i = 0; i < 6; i++) {
            const option = document.createElement('option');
            option.value = i;
            option.textContent = getReagentName(i);
            select.appendChild(option);
        }
    }

    /**
     * @brief Otwiera modal konfiguracji reagentów i wypełnia aktualnymi wartościami.
     */
    function openConfigModal() {
        // Wypełnij pola aktualnymi nazwami reagentów
        for (let i = 1; i <= 6; i++) {
            const input = document.getElementById(`reagent-${i}`);
            if (input) {
                input.value = reagentNames[i] || `Reagent_${i}`;
            }
        }
        configModal.style.display = 'flex';
    }

    /**
     * @brief Zamyka modal konfiguracji reagentów.
     */
    function closeConfigModal() {
        configModal.style.display = 'none';
    }

    /**
     * @brief Zapisuje konfigurację reagentów na serwerze.
     */
    async function saveReagentConfig() {
        const config = {};
        for (let i = 1; i <= 6; i++) {
            const input = document.getElementById(`reagent-${i}`);
            if (input) {
                config[i] = input.value.trim() || `Reagent_${i}`;
            }
        }

        try {
            const response = await fetch('/api/reagent-config/save', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: new URLSearchParams({
                    config: JSON.stringify(config)
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.text();
            console.log("Reagent configuration saved:", result);
            
            // Aktualizuj cache
            reagentNames = config;
            
            // Zamknij modal
            closeConfigModal();
            
            // Odśwież listę kroków aby pokazać nowe nazwy
            renderProgramList();
            
            // Aktualizuj opcje w select elementach
            updateReagentSelectOptions();
            
        } catch (error) {
            console.error("Error saving reagent configuration:", error);
            alert("Błąd podczas zapisywania konfiguracji reagentów.");
        }
    }

    /**
     * @brief Zwraca nazwę reagenta dla danego ID.
     */
    function getReagentName(reagentId) {
        const id = reagentId + 1; // Konwertuj z 0-based na 1-based
        return reagentNames[id] || `Reagent_${id}`;
    }

    /**
     * @brief Obsługuje kliknięcie przycisku zaworu.
     */
    function handleValveButtonClick(buttonGroupId, clickedButton) {
        console.log('Valve button clicked:', buttonGroupId, clickedButton.dataset.valve);
        const buttonGroup = document.getElementById(buttonGroupId);
        if (!buttonGroup) {
            console.error('Button group not found:', buttonGroupId);
            return;
        }

        // Sprawdź czy to wielokrotny wybór
        if (clickedButton.classList.contains('multi-select')) {
            // Toggle selection dla wielokrotnego wyboru
            clickedButton.classList.toggle('selected');
        } else {
            // Pojedynczy wybór - usuń wszystkie i wybierz jeden
            buttonGroup.querySelectorAll('.valve-btn').forEach(btn => {
                btn.classList.remove('selected');
            });
            clickedButton.classList.add('selected');
        }
    }



    /**
     * @brief Pobiera wszystkie wybrane wartości zaworów z grupy przycisków.
     */
    function getSelectedValveValues(buttonGroupId) {
        const buttonGroup = document.getElementById(buttonGroupId);
        if (!buttonGroup) return [];

        const selectedButtons = buttonGroup.querySelectorAll('.valve-btn.selected');
        return Array.from(selectedButtons).map(btn => parseInt(btn.dataset.valve));
    }

    /**
     * @brief Pobiera wybraną wartość zaworu z grupy przycisków.
     */
    function getSelectedValveValue(buttonGroupId) {
        const buttonGroup = document.getElementById(buttonGroupId);
        if (!buttonGroup) return 0;

        const selectedButton = buttonGroup.querySelector('.valve-btn.selected');
        return selectedButton ? parseInt(selectedButton.dataset.valve) : 0;
    }

    async function updateStatus() {
        try {
            const response = await fetch('/api/status');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();

            statusReagentValvePos.textContent = translateValvePosition(data.reagent_valve_position);
            statusReagentValveState.textContent = translateValveState(data.reagent_valve_state);
            statusColumnValvePos.textContent = translateValvePosition(data.column_valve_position);
            statusColumnValveState.textContent = translateValveState(data.column_valve_state);
            statusPumpFlowRate.textContent = data.pump_speed.toFixed(2);
            statusPumpVolume.textContent = data.pump_volume.toFixed(2);
            statusProgram.textContent = data.running ? `Uruchomiony (Krok ${data.program_step_idx + 1})` : 'Zatrzymany';
            statusPumpDirection.textContent = data.pump_speed >= 0 ? "Normalny" : "Odwrócony";

            setProgramEditorLock(data.running);
            handleProgramTimer(data.running, data.program_step_idx, data.program_step_progress);

        } catch (error) {
            console.error("Błąd podczas aktualizacji statusu:", error);
            statusProgram.textContent = 'Błąd połączenia';
        }
    }

    async function sendCommand(url, body, isJson = false) {
        try {
            const headers = {};
            let processedBody = body;
            if (isJson) {
                headers['Content-Type'] = 'application/json';
                processedBody = JSON.stringify(body);
            } else {
                headers['Content-Type'] = 'application/x-www-form-urlencoded';
                processedBody = new URLSearchParams(body);
            }
            const response = await fetch(url, { method: 'POST', headers, body: processedBody });
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            console.log(await response.text());
            setTimeout(updateStatus, 250);
        } catch (error) {
            console.error(`Błąd podczas wysyłania komendy do ${url}:`, error);
        }
    }

    // --- LOGIKA EDYTORA PROGRAMU ---
    
    function renderProgramList() {
        programStepsList.innerHTML = '';
        currentProgram.forEach((step, index) => {
            const listItem = document.createElement('li');
            let description = '';
            if (step.type === 'flush') {
                const reagentName = getReagentName(step.reagent);
                description = `Krok ${index + 1}: Płukanie. Reagent: <b>${reagentName}</b> Kolumna: <b>${step.column + 1}</b> Przepływ: <b>${step.pump_speed} ml/min</b> Czas: <b>${step.duration_ms / 1000}s</b>`;
            } else if (step.type === 'wait') {
                description = `Krok ${index + 1}: Czekaj. Czas: <b>${step.duration_ms / 1000}s</b>`;
            }
            listItem.innerHTML = `
                <div class="step-content">
                    <svg class="drag-handle" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>
                    <span class="step-timer timer-elapsed">00:00</span>
                    <span class="step-description">${description}</span>
                    <span class="step-timer timer-remaining">00:00</span>
                    <div class="step-actions">
                        <button class="btn-edit" data-index="${index}">Edytuj</button>
                        <button class="btn-delete" data-index="${index}">Usuń</button>
                    </div>
                </div>
                <div class="progress-bar-container">
                    <div class="progress-bar-fill"></div>
                </div>
            `;
            programStepsList.appendChild(listItem);
        });
    }

    function setProgramEditorLock(isLocked) {
        programCard.classList.toggle('program-locked', isLocked);
        if (sortable) {
            sortable.option('disabled', isLocked);
        }
    }

    function handleProgramTimer(isRunning, activeStepIndex, progress) {
        if (isRunning) {
            if (activeStepData.index !== activeStepIndex) {
                activeStepData.index = activeStepIndex;
                activeStepData.totalDuration = currentProgram[activeStepIndex]?.duration_ms || 0;
                const elapsedDuration = activeStepData.totalDuration * (progress / 255);
                activeStepData.startTime = Date.now() - elapsedDuration;
            }
            if (!programTimerInterval) {
                programTimerInterval = setInterval(updateTimersUI, 100);
            }
        } else {
            if (programTimerInterval) {
                clearInterval(programTimerInterval);
                programTimerInterval = null;
                activeStepData.index = -1;
                const steps = programStepsList.querySelectorAll('li');
                steps.forEach(step => {
                    step.classList.remove('active-step');
                    step.querySelector('.progress-bar-fill').style.width = '0%';
                    step.querySelector('.timer-elapsed').textContent = "00:00";
                    step.querySelector('.timer-remaining').textContent = "00:00";
                });
            }
        }
    }

    function updateTimersUI() {
        if (activeStepData.index === -1) return;
        
        const steps = programStepsList.querySelectorAll('li');
        const activeStepElement = steps[activeStepData.index];
        if (!activeStepElement) return;

        const elapsedMs = Date.now() - activeStepData.startTime;
        const remainingMs = activeStepData.totalDuration - elapsedMs;
        const progressPercent = Math.min((elapsedMs / activeStepData.totalDuration) * 100, 100);

        steps.forEach((step, index) => {
            step.classList.remove('active-step');
            if (index < activeStepData.index) {
                step.querySelector('.progress-bar-fill').style.width = '100%';
            } else if (index === activeStepData.index) {
                step.classList.add('active-step');
                step.querySelector('.progress-bar-fill').style.width = `${progressPercent}%`;
                step.querySelector('.timer-elapsed').textContent = formatTime(elapsedMs);
                step.querySelector('.timer-remaining').textContent = formatTime(remainingMs);
            } else {
                step.querySelector('.progress-bar-fill').style.width = '0%';
            }
        });
    }

    function openEditModal(index) {
        const step = currentProgram[index];
        if (!step) return;

        editingStepIndex = index;
        modalTitle.textContent = `Edytuj Krok ${index + 1}`;
        
        let formHtml = '';
        if (step.type === 'flush') {
            formHtml = `
                <div class="form-group">
                    <label for="edit-reagent">Reagent</label>
                    <select id="edit-reagent">
                        ${Array.from({length: 6}, (_, i) => 
                            `<option value="${i}" ${i === step.reagent ? 'selected' : ''}>${getReagentName(i)}</option>`
                        ).join('')}
                    </select>
                </div>
                <div class="form-group">
                    <label>Kolumna:</label>
                    <div class="button-grid" id="edit-column-buttons">
                        ${Array.from({length: 6}, (_, i) => 
                            `<button class="valve-btn ${i === step.column ? 'selected' : ''}" data-valve="${i}">${i + 1}</button>`
                        ).join('')}
                    </div>
                </div>
                <div class="form-group">
                    <label for="edit-flow-rate">Przepływ (ml/min)</label>
                    <input type="number" id="edit-flow-rate" step="0.1" min="-10.0" max="10.0" value="${step.pump_speed}">
                </div>
                <div class="form-group">
                    <label for="edit-duration">Czas trwania (s)</label>
                    <input type="number" id="edit-duration" min="1" value="${step.duration_ms / 1000}">
                </div>
            `;
        } else if (step.type === 'wait') {
            formHtml = `
                <div class="form-group">
                    <label for="edit-duration">Czas trwania (s)</label>
                    <input type="number" id="edit-duration" min="1" value="${step.duration_ms / 1000}">
                </div>
            `;
        }
        modalBody.innerHTML = formHtml;
        editModal.style.display = 'flex';

        // Event listeners dla przycisków w modalu są obsługiwane przez delegację zdarzeń

        // Dodaj walidację do dynamicznie utworzonych pól w modalu
        const modalInputs = modalBody.querySelectorAll('input[type="number"]');
        modalInputs.forEach(input => {
            input.addEventListener('blur', validateInputOnBlur);
        });
    }

    function closeEditModal() {
        editModal.style.display = 'none';
        editingStepIndex = -1;
    }

    btnSaveChanges.addEventListener('click', () => {
        if (editingStepIndex === -1) return;

        const step = currentProgram[editingStepIndex];
        if (step.type === 'flush') {
            step.reagent = parseInt(document.getElementById('edit-reagent').value);
            step.column = getSelectedValveValue('edit-column-buttons');
            step.pump_speed = parseFloat(document.getElementById('edit-flow-rate').value);
            step.duration_ms = parseInt(document.getElementById('edit-duration').value) * 1000;
        } else if (step.type === 'wait') {
            step.duration_ms = parseInt(document.getElementById('edit-duration').value) * 1000;
        }
        
        renderProgramList();
        closeEditModal();
    });

    btnCancelEdit.addEventListener('click', closeEditModal);

    btnAddFlushStep.addEventListener('click', () => {
        const selectedColumns = getSelectedValveValues('prog-column-buttons');
        
        if (selectedColumns.length === 0) {
            alert('Proszę wybrać przynajmniej jedną kolumnę.');
            return;
        }

        // Sortuj kolumny według numeracji
        selectedColumns.sort((a, b) => a - b);

        // Utwórz osobny krok dla każdej wybranej kolumny
        selectedColumns.forEach(columnId => {
            const newStep = {
                type: 'flush',
                reagent: parseInt(progReagent.value),
                column: columnId,
                pump_speed: parseFloat(progFlowRate.value),
                duration_ms: parseInt(progFlushDuration.value) * 1000
            };
            currentProgram.push(newStep);
        });

        renderProgramList();
    });

    btnAddWaitStep.addEventListener('click', () => {
        const newStep = {
            type: 'wait',
            duration_ms: parseInt(progWaitDuration.value) * 1000
        };
        currentProgram.push(newStep);
        renderProgramList();
    });

    programStepsList.addEventListener('click', (event) => {
        if (event.target.classList.contains('btn-delete')) {
            const indexToRemove = parseInt(event.target.getAttribute('data-index'));
            currentProgram.splice(indexToRemove, 1);
            renderProgramList();
        }
        if (event.target.classList.contains('btn-edit')) {
            const indexToEdit = parseInt(event.target.getAttribute('data-index'));
            openEditModal(indexToEdit);
        }
    });

    btnRunProgram.addEventListener('click', async () => {
        if (currentProgram.length === 0) {
            alert("Program jest pusty. Dodaj przynajmniej jeden krok.");
            return;
        }
        await sendCommand('/api/program/upload', currentProgram, true);
        await sendCommand('/api/program/run', {});
    });

    btnStopProgram.addEventListener('click', () => {
        sendCommand('/api/program/stop', {});
    });

    btnClearProgram.addEventListener('click', () => {
        if (currentProgram.length === 0) {
            alert("Program jest już pusty.");
            return;
        }
        if (confirm("Czy na pewno chcesz usunąć wszystkie kroki z aktualnego programu? Tej operacji nie można cofnąć.")) {
            currentProgram = [];
            renderProgramList();
            console.log("Program został wyczyszczony w interfejsie.");
        }
    });

    // --- Zapis/Odczyt Programu ---
    btnSaveProgram.addEventListener('click', () => {
        if (currentProgram.length === 0) {
            alert("Program jest pusty. Nie ma czego zapisywać.");
            return;
        }
        const dataStr = JSON.stringify(currentProgram, null, 2);
        const dataBlob = new Blob([dataStr], {type: "application/json"});
        const url = URL.createObjectURL(dataBlob);
        const link = document.createElement('a');
        link.download = 'program.json';
        link.href = url;
        link.click();
        URL.revokeObjectURL(url);
    });

    function handleFile(file) {
        if (!file || !file.type.match('application/json')) {
            alert("Proszę wybrać plik w formacie .json");
            return;
        }
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const loadedProgram = JSON.parse(e.target.result);
                if (Array.isArray(loadedProgram)) {
                    currentProgram = loadedProgram;
                    renderProgramList();
                } else {
                    alert("Nieprawidłowy format pliku. Oczekiwano tablicy kroków.");
                }
            } catch (error) {
                alert("Błąd podczas parsowania pliku JSON.");
                console.error(error);
            }
        };
        reader.readAsText(file);
    }

    btnLoadProgram.addEventListener('click', () => {
        loadProgramInput.click();
    });

    loadProgramInput.addEventListener('change', (event) => {
        handleFile(event.target.files[0]);
        event.target.value = ''; // Resetuj input
    });

    // Obsługa Drag and Drop
    dropZone.addEventListener('dragover', (event) => {
        event.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (event) => {
        event.preventDefault();
        dropZone.classList.remove('dragover');
        if (event.dataTransfer.files.length) {
            handleFile(event.dataTransfer.files[0]);
        }
    });


    // --- EVENT LISTENERS (Sterowanie ręczne) ---
    btnSetValves.addEventListener('click', () => {
        console.log('Set valves button clicked');
        const reagentId = getSelectedValveValue('reagent-valve-buttons');
        const columnId = getSelectedValveValue('column-valve-buttons');
        console.log('Selected valves:', reagentId, columnId);
        sendCommand('/api/manual/valves', {
            reagent_valve_id: reagentId,
            column_valve_id: columnId
        });
    });

    btnSetPump.addEventListener('click', () => {
        console.log('Set pump button clicked');
        sendCommand('/api/manual/pump', {
            pump_cmd: pumpFlowRateInput.value,
            acceleration: pumpAccelInput.value
        });
    });

    btnStopPump.addEventListener('click', () => {
        sendCommand('/api/manual/pump', { pump_cmd: 0.0, acceleration: 10.0 });
    });

    btnReversePump.addEventListener('click', () => {
        const currentFlow = parseFloat(pumpFlowRateInput.value);
        const newFlow = -currentFlow;
        pumpFlowRateInput.value = newFlow.toFixed(2);
        sendCommand('/api/manual/pump', {
            pump_cmd: newFlow,
            acceleration: pumpAccelInput.value
        });
    });

    // Event listeners dla konfiguracji reagentów
    btnOpenConfig.addEventListener('click', openConfigModal);
    btnSaveConfig.addEventListener('click', saveReagentConfig);
    btnCancelConfig.addEventListener('click', closeConfigModal);

    // Zamykanie modali przez kliknięcie poza nimi
    configModal.addEventListener('click', (event) => {
        if (event.target === configModal) {
            closeConfigModal();
        }
    });

    editModal.addEventListener('click', (event) => {
        if (event.target === editModal) {
            closeEditModal();
        }
    });

    // Debug: sprawdź czy wszystkie elementy są znalezione
    console.log('Elements found:', {
        pumpFlowRateInput: !!pumpFlowRateInput,
        pumpAccelInput: !!pumpAccelInput,
        btnSetPump: !!btnSetPump,
        btnSetValves: !!btnSetValves,
        progReagent: !!progReagent,
        progFlowRate: !!progFlowRate,
        progFlushDuration: !!progFlushDuration,
        btnAddFlushStep: !!btnAddFlushStep
    });

    // Debug: sprawdź przyciski zaworów
    console.log('Valve buttons found:', {
        reagentButtons: document.querySelectorAll('#reagent-valve-buttons .valve-btn').length,
        columnButtons: document.querySelectorAll('#column-valve-buttons .valve-btn').length,
        progColumnButtons: document.querySelectorAll('#prog-column-buttons .valve-btn').length
    });

    // Inicjalizacja
    sortable = new Sortable(programStepsList, {
        animation: 150,
        handle: '.drag-handle',
        ghostClass: 'sortable-ghost',
        onEnd: function (evt) {
            const [movedItem] = currentProgram.splice(evt.oldIndex, 1);
            currentProgram.splice(evt.newIndex, 0, movedItem);
            renderProgramList();
        }
    });

    setInterval(updateStatus, 1000);
    
    // Event listeners dla przycisków zaworów - bezpośrednie dodanie
    document.querySelectorAll('.valve-btn').forEach(button => {
        button.addEventListener('click', (event) => {
            console.log('Valve button clicked directly');
            const buttonGroup = event.target.closest('.button-grid');
            if (buttonGroup) {
                const buttonGroupId = buttonGroup.id;
                handleValveButtonClick(buttonGroupId, event.target);
            }
        });
    });


    
    // Pobierz program i konfigurację reagentów z serwera przy starcie
    Promise.all([
        loadProgramFromServer(),
        loadReagentConfigFromServer()
    ]).then(() => {
        updateStatus();
    });
});
