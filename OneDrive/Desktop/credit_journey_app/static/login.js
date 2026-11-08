// These messages stay in French even when the browser interface uses another language.
document.addEventListener('input', event => {event.target.setCustomValidity?.('');}, true);
document.addEventListener('invalid', event => {
  const field = event.target;
  if (typeof field.setCustomValidity !== 'function') return;
  field.setCustomValidity('');
  const state = field.validity;
  let message = 'Veuillez saisir une valeur valide.';
  if (state.valueMissing) message = 'Veuillez renseigner ce champ.';
  else if (state.tooShort) message = `Veuillez saisir au moins ${field.minLength} caractères.`;
  else if (state.tooLong) message = `Veuillez saisir au maximum ${field.maxLength} caractères.`;
  else if (state.patternMismatch) message = 'Utilisez de 3 à 50 lettres non accentuées, chiffres, points, tirets ou traits de soulignement.';
  field.setCustomValidity(message);
}, true);
document.getElementById('authForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const error = document.getElementById('authError');
  const button = document.getElementById('authSubmit');
  const password = document.getElementById('password').value;
  error.hidden = true;
  if (form.dataset.setup === 'true' && password !== document.getElementById('confirmPassword').value) {
    error.textContent = 'Les mots de passe ne correspondent pas.';
    error.hidden = false;
    return;
  }
  button.disabled = true;
  try {
    let response;
    try {response = await fetch(`/api/auth/${form.dataset.setup === 'true' ? 'setup' : 'login'}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]').content},
      body: JSON.stringify({username: document.getElementById('username').value, password}),
    });} catch {throw new Error('Connexion au serveur impossible. Vérifiez votre connexion, puis réessayez.');}
    const result = await response.json().catch(() => ({error:'Réponse du serveur illisible. Actualisez la page, puis réessayez.'}));
    if (!response.ok) throw new Error(result.error || 'Impossible de vous connecter. Veuillez réessayer.');
    window.location.assign('/');
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
  } finally {
    button.disabled = false;
  }
});
