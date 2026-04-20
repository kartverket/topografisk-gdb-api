import matplotlib.pyplot as plt

x_py = [39404, 52808, 41467, 58466, 58145, 41249]
y_py = [9.98, 13.53, 10.49, 14.77, 15.80, 9.81]

x_jav = [42088, 52304, 51258, 40834, 35296, 46030]
y_jav = [6.30, 6.64, 6.12, 4.82, 4.54, 4.71]

plt.plot(x_py, y_py, 'ro', label='Python')
plt.plot(x_jav, y_jav, 'bo', label='Java')
plt.legend()
plt.axis((30000, 60000, 0, 20))
plt.xlabel('Response size (kb)')
plt.ylabel('Response time (s)')
plt.show()
