/*
    This mechanism retrieves the water level in the enabled tanks and displays them on the home page.
*/

document.addEventListener('DOMContentLoaded', function() {
    if (window.location.pathname == "/") { 
    if ($('#displayScheduleDate').length > 0) {     // Verify the schedule is available (i.e. not in Manual mode)
    var style = document.createElement('style');    // Dynamic addition of CSS
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
            height: 400px;
            border: 3px solid #2E3959;
            border-radius: 10px;
            overflow: hidden;
            background-color: #ddd;
        }

        .well-wrapper {
            text-align: left;
            margin-bottom: 20px;
        }

        .well-wrapper h3 {
            margin-bottom: 10px;
            font-size: 18px;
            color: #2E3959;
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
            color: #2E3959;
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
                    <h3><span id="name1"></span></h3>
                    <div class="well">
                        <div class="water" id="water1"></div>
                        <div class="label" id="label1"></div>
                    </div>
                </div>
                <div class="well-wrapper">
                    <h3><span id="name2"></span></h3>
                    <div class="well">
                        <div class="water" id="water2"></div>
                        <div class="label" id="label2"></div>
                    </div>
                </div>
                <div class="well-wrapper">
                    <h3><span id="name3"></span></h3>
                    <div class="well">
                        <div class="water" id="water3"></div>
                        <div class="label" id="label3"></div>
                    </div>
                </div>
                <div class="well-wrapper">
                    <h3><span id="name4"></span></h3>
                    <div class="well">
                        <div class="water" id="water4"></div>
                        <div class="label" id="label4"></div>
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

    // Adding an event listener for tank clicks
    document.querySelectorAll('.well').forEach((well, index) => {
        function openLink() {
            const urls = [
                "/plugins/current_loop_tanks_monitor/graph?q=1", 
                "/plugins/current_loop_tanks_monitor/graph?q=2", 
                "/plugins/current_loop_tanks_monitor/graph?q=3", 
                "/plugins/current_loop_tanks_monitor/graph?q=4"
            ];
            window.location.href = urls[index]; 
        }
        
        well.addEventListener('click', openLink);
        well.addEventListener('touchend', openLink);
    });
});     

function updateWell(wellId, levelCm, maxHeightCm, maxVolume, voltage, name, enabled) {
    var wellWrapper = jQuery('#name' + wellId).closest('.well-wrapper');

    if (!wellWrapper.length) {
        console.error('Element not found for well ' + wellId);
        return;
    }

    if (!enabled) {
        wellWrapper.hide();  // Hide tank if disabled
        return;
    } else {
        wellWrapper.show();  // Show tank if enabled
    }

    var wellElement = jQuery('#water' + wellId);
    if (wellElement.length === 0) {
        console.error('Water element not found for well ' + wellId);
        return;
    }

    const levelPercent = (levelCm / maxHeightCm) * 100;
    const volume = (levelCm / maxHeightCm) * maxVolume;

    // Refresh height
    wellElement.css('height', levelPercent + '%');

    // Set name for tank
    jQuery('#name' + wellId).text(name);

    jQuery('#label' + wellId).html(`
        <p><span id="levelCm${wellId}">${Math.round(levelCm)}</span> cm</p>
        <p><span id="levelPercent${wellId}">${Math.round(levelPercent)}</span> %</p>
        <p><span id="volume${wellId}">${Math.round(volume)}</span> l</p>
        <p><span id="voltage${wellId}">${voltage.toFixed(3)}</span> V</p>
    `);
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
                    var tankEnabled = tank.use !== undefined ? tank.use : 0;
                    console.log('Tank ' + i + ': ', tank);
                    updateWell(i, level, maxHeightCm, maxVolume, voltage, name, tankEnabled);
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
            updateAllWells();
            observer = new MutationObserver(updateAllWells);
            observer.observe($('#displayScheduleDate')[0], {characterData: true, childList:true, subTree: true});
        }
    }
});