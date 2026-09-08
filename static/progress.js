function formatEta(sec) {
  if (sec == null) return null;
  if (sec < 45) return Math.round(sec) + "s";
  return Math.round(sec / 60) + "m";
}

function startTrackedJob(url, formData, opts) {
  var overlay = document.getElementById("loadingOverlay");
  var fill = document.getElementById("progressFill");
  var meta = document.getElementById("loadingMeta");
  var title = document.getElementById("loadingTitle");

  overlay.classList.remove("hidden");
  title.textContent = opts.title || "Working…";
  fill.style.width = "0%";
  meta.textContent = "Starting…";

  fetch(url, { method: "POST", body: formData })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.error) {
        overlay.classList.add("hidden");
        alert(data.error);
        return;
      }
      poll(data.task_id);
    })
    .catch(function () {
      overlay.classList.add("hidden");
      alert("Could not start the job. Please try again.");
    });

  function poll(taskId) {
    fetch("/status/" + taskId)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error && !data.done) {
          overlay.classList.add("hidden");
          alert(data.error);
          return;
        }
        var pct = Math.round(data.percent || 0);
        fill.style.width = pct + "%";
        var eta = formatEta(data.eta_seconds);
        meta.textContent = pct + "%" +
          (data.message ? " • " + data.message : "") +
          (eta ? " • about " + eta + " left" : "");

        if (data.done) {
          if (data.error) {
            overlay.classList.add("hidden");
            alert(data.error);
            return;
          }
          fill.style.width = "100%";
          meta.textContent = "100% • Done";
          if (opts.onDone) {
            opts.onDone(data, overlay);
          } else {
            overlay.classList.add("hidden");
          }
        } else {
          setTimeout(function () { poll(taskId); }, 700);
        }
      });
  }
}
