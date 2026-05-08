export function maskPatientName(name: string) {
  return name
    .split(" ")
    .map((part) => `${part.charAt(0)}***`)
    .join(" ");
}

export function getPatientInitials(name: string) {
  return name
    .split(" ")
    .map((part) => part.charAt(0))
    .join("")
    .slice(0, 2)
    .toUpperCase();
}
