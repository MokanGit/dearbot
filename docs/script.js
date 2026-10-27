const revealElements = document.querySelectorAll(".reveal");

if ("IntersectionObserver" in window) {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    },
    { threshold: 0.12 }
  );

  revealElements.forEach((element, index) => {
    element.style.transitionDelay = `${Math.min(index % 4, 3) * 70}ms`;
    observer.observe(element);
  });
} else {
  revealElements.forEach((element) => element.classList.add("is-visible"));
}

document.querySelectorAll("[data-year]").forEach((element) => {
  element.textContent = new Date().getFullYear();
});

document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", async () => {
    const originalLabel = button.textContent;

    try {
      await navigator.clipboard.writeText(button.dataset.copy);
      button.textContent = "Copied";
    } catch {
      button.textContent = "Select command above";
    }

    window.setTimeout(() => {
      button.textContent = originalLabel;
    }, 1800);
  });
});

const personaLab = document.querySelector("[data-persona-lab]");

if (personaLab) {
  const traitOrder = [
    "openness",
    "conscientiousness",
    "extraversion",
    "agreeableness",
    "neuroticism",
  ];
  const traitLabels = {
    openness: "Openness",
    conscientiousness: "Conscientiousness",
    extraversion: "Extraversion",
    agreeableness: "Agreeableness",
    neuroticism: "Neuroticism",
  };
  const presets = {
    operator: [58, 90, 52, 76, 18],
    maverick: [96, 38, 72, 44, 48],
    executive: [70, 86, 84, 55, 16],
    dark: [58, 92, 82, 4, 5],
  };
  const sliders = [...personaLab.querySelectorAll("[data-trait]")];
  const radarShape = personaLab.querySelector("[data-radar-shape]");
  const personaName = personaLab.querySelector("[data-persona-name]");
  const personaSummary = personaLab.querySelector("[data-persona-summary]");
  const fitScore = personaLab.querySelector("[data-fit-score]");
  const fitLabel = personaLab.querySelector("[data-fit-label]");
  const systemVerdict = personaLab.querySelector("[data-system-verdict]");
  const strongestSignal = personaLab.querySelector("[data-strongest-signal]");

  const archetypeFor = (values) => {
    const [o, c, e, a, n] = values;

    if (a <= 12 && n <= 15 && c >= 80 && e >= 65) {
      return {
        name: "Corporate Psychopath™",
        summary:
          "Calm, disciplined, charming and almost entirely untroubled by other people's feelings. Quarterly results should be excellent.",
      };
    }
    if (n >= 78) {
      return {
        name: "The Live Wire",
        summary:
          "Vigilant, emotionally responsive and prepared for every possible failure mode, including several that do not exist yet.",
      };
    }
    if (o >= 82 && c < 55) {
      return {
        name: "Creative Wildcard",
        summary:
          "Inventive, energetic and allergic to the phrase ‘we have always done it this way’—and occasionally to the delivery date.",
      };
    }
    if (c >= 82 && a >= 60 && n <= 40) {
      return {
        name: "Trusted Operator",
        summary:
          "Methodical, composed and collaborative. The profile every hiring panel claims to want until someone asks an inconvenient question.",
      };
    }
    if (e >= 76 && c >= 65 && n <= 45) {
      return {
        name: "Boardroom Catalyst",
        summary:
          "Visible, decisive and impressively comfortable beside a quarterly target. Likely to call a difficult week ‘good momentum’.",
      };
    }
    if (a >= 78) {
      return {
        name: "Diplomatic Builder",
        summary:
          "Patient, generous and very good at aligning stakeholders who all believe the meeting was their idea.",
      };
    }
    if (o <= 35 && c >= 70) {
      return {
        name: "Reliable Traditionalist",
        summary:
          "Structured, consistent and unlikely to deploy a paradigm shift before checking whether the previous paradigm still works.",
      };
    }
    return {
      name: "Adaptive Generalist",
      summary:
        "Balanced enough to pass, distinctive enough to discuss, and human enough to contradict the graph before lunch.",
    };
  };

  const renderPersona = () => {
    const values = traitOrder.map((trait) => {
      const slider = personaLab.querySelector(`[data-trait="${trait}"]`);
      const value = Number(slider.value);
      slider.style.setProperty("--value", `${value}%`);
      personaLab.querySelector(`[data-output="${trait}"]`).textContent = value;
      return value;
    });

    const points = values.map((value, index) => {
      const angle = ((-90 + index * 72) * Math.PI) / 180;
      const radius = 14 + value * 0.64;
      return `${(100 + Math.cos(angle) * radius).toFixed(1)},${(100 + Math.sin(angle) * radius).toFixed(1)}`;
    });
    radarShape.setAttribute("points", points.join(" "));

    const optimisation = Math.round(
      values.reduce((total, value) => total + Math.abs(value - 50), 0) / 2.5
    );
    const strongestIndex = values.reduce(
      (bestIndex, value, index) => value > values[bestIndex] ? index : bestIndex,
      0
    );
    const archetype = archetypeFor(values);

    personaName.textContent = archetype.name;
    personaSummary.textContent = archetype.summary;
    fitScore.textContent = optimisation;
    strongestSignal.textContent = traitLabels[traitOrder[strongestIndex]];

    if (optimisation >= 72) {
      fitLabel.textContent = "Suspiciously specific";
      systemVerdict.textContent = "Perfect answers detected. Humanity under review.";
    } else if (optimisation >= 46) {
      fitLabel.textContent = "Deliberately shaped";
      systemVerdict.textContent = "Strong persona fit. Conveniently strong.";
    } else {
      fitLabel.textContent = "Plausibly human";
      systemVerdict.textContent = "Employable, nuanced and statistically untidy.";
    }
  };

  sliders.forEach((slider) => {
    slider.addEventListener("input", () => {
      personaLab.querySelectorAll("[data-preset]").forEach((button) => button.classList.remove("is-active"));
      renderPersona();
    });
  });

  personaLab.querySelectorAll("[data-preset]").forEach((button) => {
    button.addEventListener("click", () => {
      const values = presets[button.dataset.preset];
      sliders.forEach((slider, index) => {
        slider.value = values[index];
      });
      personaLab.querySelectorAll("[data-preset]").forEach((presetButton) => {
        presetButton.classList.toggle("is-active", presetButton === button);
      });
      renderPersona();
    });
  });

  renderPersona();
}
