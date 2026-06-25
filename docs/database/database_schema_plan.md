# Initial Database Plan

The application will need a relational database to store the results produced during image and video processing. At this stage, the database design is kept simple so that it can support the first working version of the system.

The main idea is that each processing run will be saved as a monitoring session. A session may contain one input image or one video file. For video files, selected frames will be processed and stored with their frame number and timestamp.

For each processed image or frame, the application will store the detected objects. Each detection will include the object class, confidence score, bounding box coordinates, and the related frame. This will make it possible to review the detection output later and calculate useful summaries.

The database will also store simple object count summaries. For example, the system should be able to save how many cars, buses, bicycles, or people were detected in a frame. Later, this can be extended to support grid-based counting, where the image is divided into regions and objects are counted in each region.

The initial database will include the following planned tables:

- `monitoring_sessions`
- `input_sources`
- `processed_frames`
- `detection_results`
- `object_count_summaries`
- `grid_cells`
- `alerts`

The first version of these tables is implemented in:

- `app/database/migrations/001_create_initial_tables.sql`

The schema is intentionally simple and uses clear foreign key relationships so that later implementation steps can store detection results, count summaries, grid counts, and alerts without changing the whole structure.

PostgreSQL will be used as the relational database system for this project. It is suitable because the application needs to store structured detection results, frame information, object counts, and monitoring sessions in separate but related tables.

Using PostgreSQL also makes the project closer to a real application environment compared with a simple file-based database.

The first version of the schema does not need to be final. It is mainly used to define how detection results will be organised before implementing the database connection in the application.

Future improvements may include indexes, CSV export, dashboard support, and more advanced alert rules.
