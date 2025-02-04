const express = require('express');
const app = express();
const PORT = process.env.PORT || 4000; // Используйте порт из переменной окружения

app.listen(PORT, () => {
  console.log(`Сервер запущен на http://localhost:${PORT}`);
});
