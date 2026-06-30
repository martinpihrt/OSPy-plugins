(function () {
    let frames = [];
    let frameIndex = 0;
    let frameTimer = null;

    function isHomePage() {
        return window.location.pathname === "/" && jQuery("#options").length > 0;
    }

    function ensureWidget() {
        if (jQuery("#chmiHomeWidget").length) {
            return;
        }

        let style = document.createElement("style");
        style.innerHTML = `
            #chmiHomeWidget {
                float: right;
                width: 318px;
                margin: 4px 8px 4px 16px;
                border: 2px solid #2E3959;
                border-radius: 4px;
                background: #ffffff;
                overflow: hidden;
                cursor: pointer;
            }

            #chmiHomeWidget img {
                display: block;
                width: 100%;
                height: auto;
            }

            #chmiHomeWidgetLabel {
                padding: 2px 6px;
                background: #2E3959;
                color: #ffffff;
                font-size: 11px;
                font-weight: bold;
                line-height: 16px;
                text-align: left;
            }

            #chmiHomeWidgetTimeline {
                display: flex;
                gap: 2px;
                padding: 3px;
                background: #f1f1f1;
            }

            #chmiHomeWidgetTimeline span {
                flex: 1;
                height: 4px;
                border-radius: 2px;
                background: #2b7f2b;
            }

            #chmiHomeWidgetTimeline span.forecast {
                background: #d69b00;
            }

            #chmiHomeWidgetTimeline span.active {
                background: #2E3959;
            }
        `;
        document.head.appendChild(style);

        let widget = jQuery(`
            <div id="chmiHomeWidget" title="CHMI meteoradar">
                <div id="chmiHomeWidgetLabel">CHMI</div>
                <img id="chmiHomeWidgetImage" alt="CHMI radar">
                <div id="chmiHomeWidgetTimeline"></div>
            </div>
        `);
        widget.on("click", function () {
            window.location.href = "/plugins/chmi/settings";
        });

        jQuery("#options").closest("#graph-container").append(widget);
    }

    function updateTimeline() {
        let timeline = jQuery("#chmiHomeWidgetTimeline");
        timeline.empty();
        for (let i = 0; i < frames.length; i++) {
            let tick = jQuery("<span></span>");
            if (frames[i].type === "forecast") {
                tick.addClass("forecast");
            }
            if (i === frameIndex) {
                tick.addClass("active");
            }
            timeline.append(tick);
        }
    }

    function showFrame() {
        if (!frames.length) {
            return;
        }

        let frame = frames[frameIndex];
        jQuery("#chmiHomeWidgetImage").attr("src", frame.url + "&_=" + new Date().getTime());
        jQuery("#chmiHomeWidgetLabel").text(frame.label);
        updateTimeline();
        frameIndex = (frameIndex + 1) % frames.length;
    }

    function loadFrames() {
        if (!isHomePage()) {
            return;
        }

        jQuery.getJSON("/plugins/chmi/animation_json", function (data) {
            if (!data.enabled || !data.frames || !data.frames.length) {
                jQuery("#chmiHomeWidget").remove();
                if (frameTimer) {
                    clearInterval(frameTimer);
                    frameTimer = null;
                }
                return;
            }

            frames = data.frames;
            if (frameIndex >= frames.length) {
                frameIndex = 0;
            }
            ensureWidget();
            if (!frameTimer) {
                showFrame();
                frameTimer = setInterval(showFrame, 1000);
            }
        });

        setTimeout(loadFrames, 30000);
    }

    jQuery(document).ready(loadFrames);
})();
