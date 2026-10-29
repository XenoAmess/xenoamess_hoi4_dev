"""Source-specific prompts for the user's explicit anonymous/placeholder directions."""
def special_source_prompt(source, authorization):
    entry = authorization["sources"][source["key"]]
    assert authorization["explicit_user_answers"] is True
    assert entry["original_png_sha256"] == source["original_png_sha256"]
    mode = entry["mode"]
    common = ("Use case: game portrait asset conversion. Image 1 is the exact original and controls composition, "
              "headgear, framing, lighting and full painted backdrop. Image 2 is the user mascot anatomy reference. "
              "Generate one independent full-resolution asset from these exact inputs. "
              "Actually observed original: " + source["description"] + "\n")
    if mode == "grayscale_mascot_silhouette":
        return common + (
            "The user explicitly requires preserving the GREY-BLACK ANONYMOUS SILHOUETTE STYLE. "
            "Change only the human anatomical outline into the recognizable compact rounded Nailong mascot head/body silhouette. "
            "Preserve this source's exact cap or fedora outline, facing direction, shoulder/collar outline, grey gradient fill, "
            "dark contour and complete textured grey backing. Rounded mascot forehead/muzzle/chin, very short broad neck, "
            "no human nose/ear outline. Keep all interior face/hair/clothing details concealed exactly as the original. "
            "No visible eyes, mouth, colored yellow skin or green irises: this explicit silhouette direction controls the palette. "
            "Do not invent a person, insignia, uniform seams, beard, visible hair, facial features, new accessories or text. "
            "Do not reuse another silhouette; follow this distinct original. One opaque painted rectangle.")
    assert mode == "mascot_placeholder_preserve_text", "Unrecognized special art direction"
    return common + (
        "The user explicitly requires retaining the DEVELOPMENT PLACEHOLDER LETTERING. "
        "Keep the exact two large white overlay rows PLACE and HOLD, their positions, scale, layout and legibility, "
        "along with all other existing cropped decoration/letter fragments and vivid magenta/green background. "
        "Convert only the existing central helmeted/masked figure into the rounded yellow Nailong mascot, "
        "green eyes with black pupils visible wherever the original equipment leaves eye openings. "
        "Retain the actual teal helmet, diagonal green stripe, breathing-mask/respirator equipment, pose, crop and lighting. "
        "No extra human occupant; the mascot wears the original equipment. No anatomical human nose, ears or fleshy lips. "
        "Keep the mascot head compact with a short broad neck under the original clothing/equipment. "
        "Do not remove, translate, correct or add text; preserve the genuine existing PLACE HOLD overlay above the character. "
        "One opaque painted rectangle, no comparison board or new watermark.")
