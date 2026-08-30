export function applyNumericFieldConstraints(input, field) {
  input.type = "number";

  if (field.type === "integer") {
    input.step = "1";
  } else if (field.step !== undefined) {
    input.step = String(field.step);
  } else {
    input.step = "any";
  }

  if (field.spinner === false || (field.type === "number" && field.step === undefined)) {
    input.classList.add("no-number-spinner");
  }
  if (field.minimum !== undefined) input.min = String(field.minimum);
  if (field.exclusive_minimum !== undefined) {
    input.dataset.exclusiveMinimum = String(field.exclusive_minimum);
    if (field.minimum === undefined) input.min = String(field.exclusive_minimum);
  }
  if (field.maximum !== undefined) input.max = String(field.maximum);
}
