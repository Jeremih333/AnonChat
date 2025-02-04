const express = require('express');
const app = express();
const PORT = process.env.PORT || 3000; // Используем PORT из окружения или 3000 по умолчанию

app.get('/', (req, res) => {
    res.send('Hello World!');
});

app.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
});
