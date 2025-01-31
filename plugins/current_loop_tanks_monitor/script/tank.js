/*
    This mechanism retrieves the water level in the enabled tanks and displays them on the home page.
*/

document.addEventListener('DOMContentLoaded', function() {
    if (window.location.pathname == "/") {
    if ($('#displayScheduleDate').length > 0) {
    // Verify the schedule is available (i.e. not in Manual mode)
    // Dynamické přidání CSS
    var style = document.createElement('style');
    style.innerHTML = `
        .well-container {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
            width: 90%;
            max-width: 1200px;
        }

        .well {
            position: relative;
            width: 200px;
            height: 400px;
            border: 5px solid #654321;
            border-radius: 10px;
            overflow: hidden;
            background-color: #ddd;
        }

        .well.disabled {
            background-color: #bbb;
        }

        .well.disabled .water {
            background-color: #ccc;
        }

        .well-wrapper {
            text-align: left;
            margin-bottom: 20px;
        }

        .well-wrapper h3 {
            margin-bottom: 10px;
            font-size: 18px;
            color: #654321;
        }

        .water {
            position: absolute;
            bottom: 0;
            width: 100%;
            height: 0;
            background-color: #1e90ff;
            transition: height 0.5s ease, background-color 0.5s ease;
        }

        .label {
            position: absolute;
            top: 10px;
            left: 10px;
            color: #000;
            font-weight: bold;
            text-align: left;
            transition: color 0.5s ease;
        }
    `;
    document.head.appendChild(style);

    // Dynamic addition of HTML for <div id="stationsdiv">
    var stationsDiv = document.getElementById('stationsdiv');
    if (stationsDiv) {
        var graphContainer = document.createElement('div');
        graphContainer.id = 'graph-container';
        graphContainer.classList.add('graph-container');
        graphContainer.innerHTML = `
            <div class="well-container">
                <div class="well-wrapper">
                    <div class="well">
                        <div class="water" id="water1"></div>
                        <div class="label" id="label1">
                            <p>Level: <span id="levelCm1">0</span> cm</p>
                            <p>Level: <span id="levelPercent1">0</span> %</p>
                            <p>Volume: <span id="volume1">0</span> l</p>
                            <p>Voltage: <span id="voltage1">0</span> V</p>
                        </div>
                    </div>
                </div>
                <div class="well-wrapper">
                    <div class="well">
                        <div class="water" id="water2"></div>
                        <div class="label" id="label2">
                            <p>Level: <span id="levelCm2">0</span> cm</p>
                            <p>Level: <span id="levelPercent2">0</span> %</p>
                            <p>Volume: <span id="volume2">0</span> l</p>
                            <p>Voltage: <span id="voltage2">0</span> V</p>
                        </div>
                    </div>
                </div>
                <div class="well-wrapper">
                    <div class="well">
                        <div class="water" id="water3"></div>
                        <div class="label" id="label3">
                            <p>Level: <span id="levelCm3">0</span> cm</p>
                            <p>Level: <span id="levelPercent3">0</span> %</p>
                            <p>Volume: <span id="volume3">0</span> l</p>
                            <p>Voltage: <span id="voltage3">0</span> V</p>
                        </div>
                    </div>
                </div>
                <div class="well-wrapper">
                    <div class="well">
                        <div class="water" id="water4"></div>
                        <div class="label" id="label4">
                            <p>Level: <span id="levelCm4">0</span> cm</p>
                            <p>Level: <span id="levelPercent4">0</span> %</p>
                            <p>Volume: <span id="volume4">0</span> l</p>
                            <p>Voltage: <span id="voltage4">0</span> V</p>
                        </div>
                    </div>
                </div>
            </div>
        `;
            stationsDiv.insertAdjacentElement('afterend', graphContainer);
        } else {
            console.error('Element with id "stationsdiv" not found.');
        }
    }
    }
});     

function updateWell(wellId, levelCm, maxHeightCm, maxVolume, voltage){
    var wellElement = jQuery('#water'+wellId);
    if(wellElement.length === 0) {
        console.error('Element not found.');
        return;
    }

    const levelPercent = (levelCm / maxHeightCm) * 100;
    const volume = (levelCm / maxHeightCm) * maxVolume;

    // Visual water height update
    wellElement.css('height', levelPercent+'%');

    // Update text values
    var levelCmElement = jQuery('#levelCm'+wellId);
    var levelPercentElement = jQuery('#levelPercent'+wellId);
    var volumeElement = jQuery('#volume'+wellId);
    var voltageElement = jQuery('#voltage'+wellId);

    if (levelCmElement.length && levelPercentElement.length && volumeElement.length && voltageElement.length){
        levelCmElement.text(Math.round(levelCm));
        levelPercentElement.text(Math.round(levelPercent));
        volumeElement.text(Math.round(volume));
        voltageElement.text(voltage.toFixed(3));
    } else {
        console.error('Elements for level and volume were not found.');
    }
}

function updateAllWells() {
    if (window.location.pathname == "/") {
        if ($('#displayScheduleDate').length > 0) {    
            jQuery.getJSON("/plugins/current_loop_tanks_monitor/data_json", function(data) {
                for (var i = 1; i < 5; i++) {
                    var tank = data['tank' + i];
                    if (!tank) {
                        console.error('Data for tank' + i + ' are missing.');
                        continue;
                    }

                    var name = tank.label || 'Unknown';
                    var maxHeightCm = tank.maxHeightCm || 1;  // We set it to 1 to avoid division by zero
                    var maxVolume = tank.maxVolume || 0;
                    var level = tank.level !== undefined ? tank.level : 0;
                    var voltage = tank.voltage !== undefined ? tank.voltage : 0;
                    console.log(name, maxHeightCm, maxVolume, level, voltage);
                    updateWell(i, level, maxHeightCm, maxVolume, voltage);
                }
            }).fail(function() {
                console.error('Failed to load JSON data.');
            });
        }
    }
}        

jQuery(document).ready(function(){
    if (window.location.pathname == "/") {
        if ($('#displayScheduleDate').length > 0) {
            // Verify the schedule is available (i.e. not in Manual mode)
            observer = new MutationObserver(updateAllWells);
            observer.observe($('#displayScheduleDate')[0], {characterData: true, childList:true, subTree: true});
        }
    }
});