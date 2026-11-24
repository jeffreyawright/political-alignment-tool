#!/bin/bash

# Install required Python packages
conda activate myenv
conda install requests beautifulsoup4 pandas numpy scipy scikit-learn

# Create a requirements.txt file
cat > requirements.txt << EOL
requests>=2.28.0
beautifulsoup4>=4.11.0
pandas>=1.4.0
numpy>=1.22.0
scipy>=1.8.0
scikit-learn>=1.0.0
EOL

# Create an environment.yml file for reproducibility
conda env export --name myenv --file environment.yml

echo "Setup complete. Required packages installed and requirements.txt created."
echo "To run the Political Alignment Tool, use: python app.py"
