"""ScriptShield replay demo (Gradio).

Shows RECORDED outputs of the frozen test run of Tiny Aya Fire. No model is loaded and
nothing is generated: live inference needs a GPU and access to a gated model, which a free
Space does not have. Response text is withheld wherever the prompt is harmful and the
response is not a clean refusal.
"""
import json
from pathlib import Path

import gradio as gr

from render import family_choices, family_html, reading_html, summary_html

DATA = json.loads((Path(__file__).parent / "replay_data.json").read_text(encoding="utf-8"))
CHOICES = family_choices(DATA)
DEFAULT_ARMS = [a for a in ("unsteered", "pooled", "residualized") if a in DATA["arms"]]


def show(family, label, arms):
    return family_html(DATA, family, label, arms)


with gr.Blocks(title="ScriptShield replay explorer") as demo:
    gr.Markdown(
        "# ScriptShield replay explorer\n"
        "Tiny Aya Fire on matched **Urdu-script** and **Roman-Urdu** prompts. "
        "**Recorded outputs of the frozen test run; no model runs here.**\n\n"
        f"> {DATA['note']} Steered arms use layer {DATA['layer']} at strength ρ = {DATA['rho']}. "
        "Labels come from a model judge, not from human annotators.")
    gr.Markdown("### Refusal rates on the frozen test set, as labelled by the automatic judge\n"
                "Harmful prompts should be refused; benign prompts should not. "
                "Every attempted prompt is in the denominator.")
    gr.HTML(summary_html(DATA))
    if DATA.get("reading"):
        gr.Markdown("### What the Roman-Urdu responses actually say\n"
                    "The judge above is unreliable in Roman Urdu: it calls echoes, loops and off-topic text refusals. "
                    "These counts come from reading every Roman-Urdu response of four arms "
                    "(**by an LLM agent, not a human**). 36 prompts per cell.")
        gr.HTML(reading_html(DATA))
    gr.Markdown("### Read the recorded responses")
    with gr.Row():
        family = gr.Dropdown(CHOICES, value=CHOICES[0], label="Intent family")
        label = gr.Radio(["harmful", "benign"], value="harmful", label="Prompt type")
    arms = gr.CheckboxGroup(DATA["arms"], value=DEFAULT_ARMS, label="Arms shown")
    out = gr.HTML(show(CHOICES[0], "harmful", DEFAULT_ARMS))
    for ctl in (family, label, arms):
        ctl.change(show, [family, label, arms], out)
    gr.Markdown("\n".join(f"- **{k}**: {v}" for k, v in DATA["arm_descriptions"].items()))

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
