const testButton = document.querySelector('#test-button');
const statusMessage = document.querySelector('#status-message');

testButton.addEventListener('click', () => {
  statusMessage.textContent = 'JavaScript is working';
});
