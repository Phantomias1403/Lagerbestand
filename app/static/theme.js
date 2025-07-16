const themeToggle = document.getElementById('theme-toggle');
if (themeToggle) {
  const updateText = () => {
    const current = document.documentElement.getAttribute('data-bs-theme') || 'light';
    themeToggle.textContent = current === 'dark' ? 'Light Mode' : 'Dark Mode';
  };
  themeToggle.addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-bs-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-bs-theme', next);
    localStorage.setItem('theme', next);
    updateText();
  });
  updateText();
}
