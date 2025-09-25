	# Set a seed for reproducibility
	set.seed(123)

	# Generate a random dataset
	x <- rnorm(100)
	data <- data.frame(
	x = x,
	y = 2 * x + rnorm(100)
	)
	if ("x" %in% colnames(data) && is.numeric(data$x) &&
		"y" %in% colnames(data) && is.numeric(data$y)) {
	# Compute basic statistics
	mean_x <- mean(data$x, na.rm = TRUE)
	mean_y <- mean(data$y, na.rm = TRUE)
	correlation <- cor(data$x, data$y, use = "complete.obs")
	# Print the statistics
	cat("Mean of x:", mean_x, "\n")
	cat("Mean of y:", mean_y, "\n")
	cat("Correlation between x and y:", correlation, "\n")

	} else {
	cat("Error: Columns 'x' and 'y' must be numeric and exist in the dataset.\n")
	}