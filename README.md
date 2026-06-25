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
- PostgreSQL
- Docker Compose for the local PostgreSQL database
- Ubuntu under WSL2
- Git and GitHub

## Development Strategy

The application is developed incrementally. The first stage focuses on image-based object detection. Later stages will add video processing, database storage, grid-based aggregation and alert logic.

## Current Status

The current development focus is the image detection prototype and the first PostgreSQL integration step. CI is configured with GitHub Actions.
