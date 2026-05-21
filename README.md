# Traffic and Crowd Monitoring Application

This project is developed as part of a BSc thesis. The application processes aerial image and video data for traffic and crowd monitoring using computer vision techniques.

## Project Aim

The aim of this project is to design and implement an application that converts aerial visual data into structured monitoring information. The system detects objects such as vehicles and people, counts them, groups them spatially, and stores the results for further analysis.

## Current Features

- Image input processing
- Object detection
- Class-wise object counting
- Annotated image output

## Planned Features

- Video frame extraction
- Grid-based spatial aggregation
- Relational database storage
- Threshold-based alert generation

## Technology Stack

- Python
- OpenCV
- YOLO object detection
- MySQL
- Ubuntu under WSL2
- Git and GitHub

## Development Strategy

The application is developed incrementally. The first stage focuses on image-based object detection. Later stages will add video processing, database storage, grid-based aggregation and alert logic.

## Current Status

The current development focus is the basic image detection prototype. Also added CI/CD workflows git hub actions.
